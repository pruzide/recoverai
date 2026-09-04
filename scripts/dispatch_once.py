import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.outbox.dispatcher import dispatch_outbox_events


if __name__ == "__main__":
    dispatched = dispatch_outbox_events()
    print(dispatched)
