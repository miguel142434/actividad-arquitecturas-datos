"""Entrada interna para callbacks de fallo, sin iniciar servicios ni cambiar marcas."""

import argparse
import json
from .spec import normalize_spec
from .tasks import event, store_client


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', required=True)
    parser.add_argument('--details', required=True)
    args = parser.parse_args()
    try:
        event(store_client(), normalize_spec(json.loads(args.spec)), 'FAILED', json.loads(args.details))
    except Exception as error:
        raise SystemExit(type(error).__name__) from None


if __name__ == '__main__': main()
