import argparse
import json

from db import get_db_connection
from services.traffic_quality import reclassify_known_bot_views


def main():
    parser = argparse.ArgumentParser(
        description="Reclassify known automated article views."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the repair. Without this flag, only preview counts.",
    )
    args = parser.parse_args()

    conn = get_db_connection()
    try:
        result = reclassify_known_bot_views(conn, apply=args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
        print(json.dumps({"applied": args.apply, **result}, sort_keys=True))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
