import ics
import os
import jinja2
import tomlkit

import election

os.makedirs("site", exist_ok=True)

env = jinja2.Environment(loader=jinja2.FileSystemLoader("templates"))

states = {}

state_index = env.get_template("state/index.html.jinja")
county_index = env.get_template("state/county/index.html.jinja")

# Load per-state data. fn for filename which is also the lower cased version of the state or county.
for fn in os.listdir("states/"):
    info_fn = os.path.join("states", fn, "info.toml")
    if not os.path.exists(info_fn):
        continue
    with open(info_fn, "r") as f:
        state_info = dict(tomlkit.loads(f.read()))
    state_info["lower_name"] = fn
    states[fn] = state_info

    # Load per-county data.
    counties = {}
    state_dir = os.path.join("states", fn)
    for county_fn in os.listdir(state_dir):
        info_fn = os.path.join(state_dir, county_fn, "info.toml")
        if not os.path.exists(info_fn):
            continue
        with open(info_fn, "r") as f:
            county_info = tomlkit.loads(f.read())
        county_info["lower_name"] = county_fn
        counties[county_fn] = county_info
    state_info["counties"] = counties

for state_lower in states:
    state_info = states[state_lower]

    all_state_dates = [d for d in election.dates if d["state"] is None or d["state"] == state_lower]

    # Load per-county data.
    counties = state_info["counties"]
    for county_lower in counties:
        county_info = counties[county_lower]
        os.makedirs(f"site/en/{state_lower}/{county_lower}", exist_ok=True)
        county_dates = [d for d in all_state_dates if d["county"] is None or d["county"] == county_lower]
        county_data = {"language": "en",
                       "state": state_info,
                       "county": dict(county_info),
                       "dates": county_dates}
        ics.generate(county_dates, f"site/en/{state_lower}/{county_lower}/voter.ics")
        county_index.stream(county_data).dump(f"site/en/{state_lower}/{county_lower}/index.html")

    county_list = list(counties.values())
    county_list.sort(key=lambda x: x["lower_name"])
    os.makedirs(f"site/en/{state_lower}", exist_ok=True)
    state_dates = [d for d in all_state_dates if d["county"] is None]
    state_data = {"language": "en",
                  "state": state_info,
                  "counties": county_list,
                  "dates": state_dates}
    ics.generate(state_dates, f"site/en/{state_lower}/voter.ics")
    ics.generate(all_state_dates, f"site/en/{state_lower}/all-voter.ics")
    state_index.stream(state_data).dump(f"site/en/{state_lower}/index.html")

state_list = list(states.values())
state_list.sort(key=lambda x: x["lower_name"])

# Render the index.
top_level = env.get_template("index.html.jinja")

federal_dates = [d for d in election.dates if d["state"] is None]
top = {"language": "en", "states": state_list, "dates": federal_dates}
ics.generate(federal_dates, f"site/en/voter.ics")
ics.generate(election.dates, f"site/en/all-voter.ics")
top_level.stream(top).dump("site/index.html")
