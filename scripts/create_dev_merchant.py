import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db import get_session_factory
from app.models import Merchant


def main():
    SessionLocal = get_session_factory()

    with SessionLocal() as session:
        with session.begin():
            merchant = Merchant(name="Dev Merchant")
            session.add(merchant)
            session.flush()

            print(merchant.id)


if __name__ == "__main__":
    main()