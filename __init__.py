import ics
from urllib.request import urlopen
import datetime
from opsdroid.matchers import match_regex
from opsdroid.skill import Skill
from cachetools import TTLCache
import pytz
from textwrap import dedent


F1BOT_COMMAND_PREFIX = "!"
F1BOT_COMMANDS = {}


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
    commands = "\n".join([f"{F1BOT_COMMAND_PREFIX}{command} - {description}" for command, description in F1BOT_COMMANDS.items()])
    help_text = dedent("""\
    Hambot understands the following commands:

    {commands}
    """).format(commands=commands)
    await message.respond(help_text)


class Formula1Events(Skill):
    """
    Parse the F1 Events calendar into a matrix bot.
    """
    def __init__(self, opsdroid, config, *args, **kwargs):
        self.cache = TTLCache(maxsize=5, ttl=60*60)  # Only retrieve the data every hour
        self.tz = datetime.UTC
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

    def get_next_event(self, session="race"):
        events = list(filter(lambda e: session in e.name.lower(), self.get_all_events()))
        return events[0]

    def next_event_info(self, session=None, display_tz=datetime.UTC):
        session = session or "race"
        event = self.get_next_event(session=session)
        start = event.begin.astimezone(display_tz).strftime("%Y-%m-%d %H:%M:%S %Z")
        return f"{event.name} {start}"

    def get_upcoming_events(timedelta=datetime.timedelta(minutes=10)):
        now = datetime.datetime.now(self.tz)
        return list(f1.cal.timeline.included(now,
                                             now+datetime.timedelta(minutes=timedelta)))

    @regex_command("next\s?(?P<session>(?:race|quali|practice))?\s?(?P<tz>.*)",
                   "Get the information about the next F1 event.",
                   friendly_command="next [race|quali|practice] [timezone]")
    async def next_event_command(self, message):
        tz = message.entities['tz']['value']
        tz = pytz.timezone(tz) if tz else datetime.UTC
        session = message.entities['session']['value']
        await message.respond(self.next_event_info(session=session, display_tz=tz))
