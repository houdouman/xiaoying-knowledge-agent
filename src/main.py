import argparse
import json
import sys
from pathlib import Path
from .agent import run

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--mode', choices=['offline','live'], default='offline')
    args = p.parse_args()
    try:
        request = json.loads(Path(args.input).read_text(encoding='utf-8-sig'))
        result = run(request, args.mode)
    except (ValueError, OSError) as exc:
        print(json.dumps({'status':'invalid_input','error':str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == '__main__':
    sys.exit(main())
