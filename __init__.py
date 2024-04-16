import datetime
from textwrap import dedent
from urllib.request import urlopen
import logging

import ics
import pytz
from cachetools import TTLCache
from opsdroid.matchers import match_regex, match_crontab
from opsdroid.skill import Skill

F1BOT_COMMAND_PREFIX = "!"
F1BOT_COMMANDS = {}


_LOGGER = logging.getLogger(__name__)


def regex_command(command, description="", friendly_command=None, **kwargs):
    """
    A decorator which wraps opsdroid's match_regex to register a command with
    the !help command.
    """
    F1BOT_COMMANDS[friendly_command or command] = description

    def decorator(func):
        return match_regex(f"^{F1BOT_COMMAND_PREFIX}{command}", **kwargs)(func)
    return decorator


@regex_command("help", "print this help message")
async def help(opsdroid, config, message):
    commands = "<br/>\n".join([f"{F1BOT_COMMAND_PREFIX}{command} - {description}" for command, description in F1BOT_COMMANDS.items()])
    help_text = dedent("""\
    F1Bot understands the following commands:<br/>

    {commands}
    """).format(commands=commands)
    await message.respond(help_text)


class Formula1Events(Skill):
    """
    Parse the F1 Events calendar into a matrix bot.
    """
    def __init__(self, opsdroid, config, *args, **kwargs):
        self.cache = TTLCache(maxsize=5, ttl=60*60)  # Only retrieve the data every hour
        self.tz = pytz.UTC
        super().__init__(opsdroid, config)

    @property
    def cal(self):
        if "cal" not in self.cache:
            resp = urlopen(self.config["calendar_url"])
            icsdata = resp.read().decode()
            cal = ics.Calendar(icsdata)
            self.cache["cal"] = cal
        return self.cache["cal"]

    def get_all_events(self):
        return list(self.cal.timeline.start_after(datetime.datetime.now(self.tz)))

    def get_next_event(self, session=None):
        events = self.get_all_events()
        if session is not None:
            events = list(filter(lambda e: session in e.name.lower(), events))
            # sprint races are stupid
            if session == "race":
                events = list(filter(lambda e: "sprint" not in e.name.lower(), events))
        return events[0]

    def next_event_info(self, session=None, display_tz=pytz.UTC):
        event = self.get_next_event(session=session)
        return self.format_event(event, display_tz)

    def format_event(self, event, display_tz=pytz.UTC):
        time_fmt = "%Y-%m-%d %H:%M:%S %Z"
        start = event.begin.astimezone(display_tz).strftime(time_fmt)
        response = f"{event.name} - {start}"
        if display_tz != pytz.UTC:
            start_utc = event.begin.astimezone(pytz.UTC).strftime(time_fmt)
            response += f" ({start_utc})"
        return response

    def get_upcoming_events(timedelta=datetime.timedelta(minutes=10)):
        now = datetime.datetime.now(self.tz)
        return list(f1.cal.timeline.included(now,
                                             now+datetime.timedelta(minutes=timedelta)))

    @regex_command("next\s?(?P<session>(?:race|quali|sprint\-quali|sprint|practice|any))?\s?(?P<tz>.*)",
                   "Get the information about the next F1 event.",
                   friendly_command="next [race|quali|sprint|sprint-quali|practice|any] [timezone]")
    async def next_event_command(self, message):
        tz = message.entities['tz']['value']
        if not tz:
            tz = await self.opsdroid.memory.get(message.user_id, None)
        try:
            tz = pytz.timezone(tz) if tz else pytz.UTC
        except pytz.UnknownTimeZoneError:
            return await message.respond(f"Unable to parse timezone {tz}")
        session = message.entities['session']['value']
        if session is None:
            session = "race"
        if session == "sprint":
            session = "sprint-race"
        session = session.replace("-", " ")
        if session == "any":
            session = None
        await message.respond(self.next_event_info(session=session, display_tz=tz))

    @regex_command("weekend",
                   "Print out the whole schedule for the weekend")
    async def weekend(self, message):
        # Get the name of the next event (and use this as the name for the "weekend")
        next_event = self.get_next_event()

        event_name = next_event.name
        # Let's hope in future years they don't change the format of the events.
        start_idx = event_name.find("FORMULA 1")
        end_idx = event_name.find(" - ")
        event_name = event_name[start_idx:end_idx]

        weekend_events = []
        for event in self.cal.events:
            if event_name in event.name:
                weekend_events.append(event)

        # send both line breaks in html and plain because plain is ignored in html
        await message.respond("\n</br>".join(
            [self.format_event(e) for e in weekend_events]
        ))

    @regex_command("settz\s?(?P<tz>.*)",
                   "Store a default timezone for your user.",
                   friendly_command="settz <timezone>")
    async def store_tz_command(self, message):
        try:
            tz = message.entities['tz']['value']
            tz = pytz.timezone(tz) if tz else pytz.UTC
        except pytz.UnknownTimeZoneError:
            return await message.respond(f"Unable to parse timezone {tz}")
        await self.opsdroid.memory.put(message.user_id, tz.zone)
        await message.respond(f"Set timezone for user {message.user} to {tz.zone}")
