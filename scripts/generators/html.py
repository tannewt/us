import copy
import jinja2
import pendulum
import datetime
import subprocess
import os
import json
import tweepy

from . import images

env = jinja2.Environment(loader=jinja2.FileSystemLoader("templates"))

state_index = env.get_template("state/index.html.jinja")
state_debug = env.get_template("state/debug.html.jinja")
county_index = env.get_template("state/county/index.html.jinja")
# Render the index.
top_level = env.get_template("index.html.jinja")
top_level_debug = env.get_template("debug.html.jinja")

git_sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True).stdout.decode("utf-8").strip()

future = datetime.datetime.now() + datetime.timedelta(days=365*4)

if "TWITTER_ACCESS_TOKENS" not in os.environ:
    with open("secrets.json", "r") as f:
        os.environ["TWITTER_ACCESS_TOKENS"] = f.read()
twitter_access_tokens = json.loads(os.environ["TWITTER_ACCESS_TOKENS"])

def debug_key(state):
    for key in ["next_reminder"]:
        if key in state:
            return state[key]["date"]
    return future

def build(
    now,
    dates,
    state=None,
    county=None,
    *,
    language="en",
    alternatives=[],
    name=None,
    description=None,
    uid=None,
    states=None,
    counties=None,
):
    if county:
        return
    upcoming_dates = [d for d in dates if d["date"].date() >= now.date()]

    if states:
        for d in upcoming_dates:
            key = "next_" + d["type"]
            if d["state"] is None:
                for s in states.values():
                    if key not in s:
                        s[key] = d
            else:
                s = states[d["state"]]
                if key not in s:
                    s[key] = d

    # Determine the next two elections.
    this_election = None
    next_election = None
    for d in upcoming_dates:
        if d["type"] == "election":
            if not this_election:
                this_election = d
            elif not next_election:
                next_election = d
            else:
                break

    # Filter down to the next reminder date, deadlines up to the next election and
    # the next election.
    next_reminder = None
    filtered_dates = []
    for d in upcoming_dates:
        if d["type"] == "election":
            if d != this_election and d != next_election:
                continue
        elif d["type"] == "deadline":
            if d["date"].date() > this_election["date"].date():
                continue
        elif d["type"] == "reminder":
            if "start_date" in d and now < d["start_date"]:
                continue
            if not next_reminder:
                next_reminder = d
            elif next_reminder["date"].date() == d["date"].date():
                if "composite" not in next_reminder:
                    next_reminder = {
                        "composite": True,
                        "reminders": [next_reminder],
                        "date": d["date"],
                        "deadline_date": d["date"]
                    }
                next_reminder["reminders"].append(d)
            continue
        filtered_dates.append(d)

    # if next_reminder and state and not county:
    #     print(state["name"])
    #     reminders = []
    #     if "composite" in next_reminder:
    #         reminders.extend(next_reminder["reminders"])
    #     else:
    #         reminders.append(next_reminder)
    #     for reminder in reminders:
    #         print("\t", reminder)

    main_date = None
    secondary_date = None
    if next_reminder:
        now = pendulum.instance(now)
        reminder_date = pendulum.instance(next_reminder["date"])
        diff = reminder_date.diff(now, False)
        next_reminder["remaining_days"] = abs(diff.in_days())
        if diff.in_days() == 0:
            main_date = "Today"
            secondary_date = reminder_date.format("(MMMM Do)")
        elif diff.in_days() == -1:
            main_date = "Tomorrow"
            secondary_date = reminder_date.format("(MMMM Do)")
        else:
            main_date = reminder_date.format("MMMM Do")
            secondary_date = reminder_date.format("(dddd)")
        if "composite" in next_reminder:
            next_reminder["state"] = [r["state"] for r in next_reminder["reminders"]]
            next_reminder["state"] = sorted(list(set(next_reminder["state"])))
            actions = sorted(list(set((r["name"] for r in next_reminder["reminders"]))))
            if len(next_reminder["state"]) > 1 and len(actions) > 1:
                next_reminder["name"] = "Check electioncal.us for deadlines"
            else:
                if all((a.startswith("Register to vote ") for a in actions)):
                    for i in range(1, len(actions)):
                        actions[i] = actions[i][len("Register to vote "):]
                next_reminder["name"] = ", ".join(actions[:-1]) + " or " + actions[-1]
                next_reminder["explanation"] = " ".join((r["explanation"] for r in next_reminder["reminders"] if "explanation" in r))
            next_reminder["name"] = next_reminder["name"].lower().capitalize()

    path = f"{language}"
    if state:
        state_lower = state["lower_name"]
        if county:
            county_lower = county["lower_name"]
            path = f"{language}/{state_lower}/{county_lower}"
        else:
            path = f"{language}/{state_lower}"

    data = {
        "alternatives": alternatives,
        "language": language,
        "dates": filtered_dates,
        "reminder": next_reminder,
        "main_date": main_date,
        "secondary_date": secondary_date,
        "path": path,
        "git_sha": git_sha
    }
    template = top_level
    debug_template = None
    filenames = [f"site/{path}/index.html"]
    if state:
        template = state_index
        data["state"] = state
        data["demonym"] = state.get("demonym", "American")
        if county:
            data["county"] = county
            data["reminder_location"] = county["name"] + ", " + state["name"]
            template = county_index
        else:
            debug_template = state_debug
            county_list = list(counties.values())
            county_list.sort(key=lambda x: x["lower_name"])
            data["reminder_location"] = state["name"]
            data["counties"] = county_list
    else:
        state_list = list(states.values())
        state_list.sort(key=lambda x: x["lower_name"])
        if next_reminder:
            if isinstance(next_reminder["state"], list):
                data["reminder_location"] = ", ".join((states[s]["name"] for s in next_reminder["state"]))
                next_reminder["explanation"] = data["reminder_location"]
            else:
                data["reminder_location"] = states[next_reminder["state"]]["name"]
        data["states"] = state_list
        data["demonym"] = "American"
        if language == "en":
            filenames.append(f"site/index.html")
        debug_template = top_level_debug

    explanation = ""
    if next_reminder:
        reminder = next_reminder["name"] + " by"
        if "explanation" in next_reminder:
            explanation = next_reminder["explanation"]
    else:
        reminder = "Help us add dates at"
        main_date = "github.com/electioncal/us"

    sec_date = None
    if secondary_date:
        sec_date = secondary_date.replace("(", "( ").replace(")", " )")

    sites = {"twitter": ("twitter_card", "Twitter Card"),
             "instagram": ("instagram", "Instagram")}
    hashtags = {
        "twitter": {
            "absentee": "#votebymail",
            "registration": "#registertovote"
        },
        "instagram": {

        }
    }
    for site in sites:
        filename, title = sites[site]
        images.render_image(
            f"site/{path}/{filename}.png",
            site,
            state=state["name"] if state else None,
            county=county["name"] if county else None,
            reminder=reminder,
            main_date=main_date,
            secondary_date=sec_date,
            explanation=explanation)
        if site == "twitter" and next_reminder and state and not county:
            tweet = False
            access_token = twitter_access_tokens[state["lower_name"]]
            secret = os.environ.get("TWITTER_SECRET_" + state["lower_name"].upper(), "")
            twitter = None
            if access_token and secret:
                print(state["lower_name"])
                auth = tweepy.OAuthHandler(os.environ["TWITTER_CONSUMER_KEY"], os.environ["TWITTER_CONSUMER_SECRET"])
                auth.set_access_token(access_token, secret)
                twitter = tweepy.API(auth)
                tweet = True
                try:
                    me = twitter.me()
                except tweepy.error.TweepError as e:
                    print()
                    for error in e.response.json()["errors"]:
                        if error["code"] != 326:
                            raise e
                        else:
                            print(state["lower_name"], "Twitter account is locked")
                    tweet = False
                if tweet:
                    print(me)
                    timeline = twitter.user_timeline()
                    tweet = len(timeline) == 0
                    for status in timeline:
                        print(status)
            mentions = []
            state_tag = ""
            if state:
                state_tag = "#" + state["lower_name"]
                for key in state:
                    if "twitter" in key:
                        handles = state[key]
                        if isinstance(handles, list):
                            mentions.extend(("@" + h for h in handles))
                        else:
                            mentions.append("@" +  handles)
            county_tag = ""
            if county:
                county_tag = "#" + county["lower_name"]
            mentions = " ".join(mentions)
            espace = ""
            if explanation:
                espace = " "
            hashtag = ""
            theme = next_reminder.get("subtype", ".").split(".", 1)[0]
            if site in hashtags and theme in hashtags[site]:
                hashtag = hashtags[site][theme]

            datetag = "#" + next_reminder["date"].strftime("%Y%m%d")

            # print(next_reminder["remaining_days"], next_reminder["subtype"])
            if tweet and twitter:
                status_text = f"{reminder} {main_date} {secondary_date}. {explanation}{espace}Learn more, subscribe and share at https://electioncal.us/{path}/ {mentions} {state_tag} {hashtag} #vote {datetag}"
                print(status_text)
                print()
                # m = twitter.media_upload(f"site/{path}/{filename}.png")
                # print(m.media_id, m)
                # twitter.update_status(status_text, media_ids=[m.media_id])
                #twitter.create_media_metadata(m.media_id, f"Hopefully eye-catching graphic that says \"{reminder} {main_date} {secondary_date}. {explanation}\"")


        if debug_template:
            debug_social = dict(data)
            debug_social["debug_name"] = title
            debug_social["filename"] = f"{filename}.png"
            if "states" in debug_social:
                debug_social["states"].sort(key=debug_key)
            debug_template.stream(debug_social).dump(f"site/{path}/debug_{site}.html")

    for filename in filenames:
        template.stream(data).dump(filename)
