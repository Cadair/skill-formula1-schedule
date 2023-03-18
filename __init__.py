import ics
from urllib.request import urlopen
import datetime

from cachetools import TTLCache


class Formula1Events():
    """
    """
    def __init__(self):
        self.cache = TTLCache(maxsize=5, ttl=60*60)  # Only retrieve the data every hour

    @property
    def cal(self):
        if "cal" not in self.cache:
            resp = urlopen(
                "https://ics.ecal.com/ecal-sub/6415faefadbc17000da55b31/Formula%201.ics"
            )
            icsdata = resp.read().decode()
            cal = ics.Calendar(icsdata)
            self.cache["cal"] = cal
        return self.cache["cal"]

    def get_next_event(self):
        return list(self.cal.timeline.start_after(datetime.datetime.now(datetime.UTC)))[0]

    def next_event_info(self, tz=datetime.UTC):
        event = self.get_next_event()
        start = event.begin.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
        return f"{event.name} {start}"




f1 = Formula1Events()
event = f1.get_next_event()
print(f1.next_event_info())
