import sys, json
try:
    data = json.load(sys.stdin)
    print('=== Recording Rules ===')
    for group in data['data']['groups']:
        print(f"Group: {group['name']}")
        for rule in group['rules']:
            if rule['type'] == 'recording':
                health = rule.get('health', 'unknown')
                print(f"  {rule['name']}: {health}")
except Exception as e:
    print(f'Error: {e}')
