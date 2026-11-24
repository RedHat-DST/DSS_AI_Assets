#!/usr/bin/env python3
import csv, json
from pathlib import Path

src = Path(__file__).parent.parent / 'output/nl_core_territory2_accounts.json'
dst = Path(__file__).parent.parent / 'output/nl_core_territory2_accounts.csv'
data = json.loads(src.read_text())
with dst.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['Id','Name','Type','BillingState','Phone','Owner'])
    w.writeheader()
    for row in data['accounts']:
        w.writerow({
            'Id': row.get('Id'),
            'Name': row.get('Name'),
            'Type': row.get('Type'),
            'BillingState': row.get('BillingState'),
            'Phone': row.get('Phone'),
            'Owner': row.get('Owner.Alias'),
        })
print(dst)
