"""
Comprehensive extraction test for DemoEntityAgent.
Covers: 8 accounting vouchers, 6 stock transactions, 8 master types, custom vouchers.

Run:  python backend/tests/test_entity_extraction.py
Exit: 0 = all passed,  1 = failures (used by pre-commit hook to block commits)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import types, re
cfg_mod = types.ModuleType('app.core.config')
cfg_mod.settings = types.SimpleNamespace(
    AI_PROVIDER='demo', GROQ_API_KEY='', OPENROUTER_API_KEY='',
    is_demo_mode=True, GROQ_MODEL='', AI_MODEL='',
)
sys.modules['app.core.config'] = cfg_mod
import app.core; app.core.config = cfg_mod

from app.agents.entity_agent import DemoEntityAgent
a = DemoEntityAgent()
RS = chr(0x20B9)  # ₹

# -----------------------------------------------------------------------------
# Test schema: (expected_type, text, check_key, expected_value_contains, date_or_None)
# date_or_None = None  → no date check for this master-entity row
# -----------------------------------------------------------------------------
TESTS = [

    # ═══════════════════════════════════════════════════════════════════════════
    # ACCOUNTING VOUCHERS  (8 types — simple + complex)
    # ═══════════════════════════════════════════════════════════════════════════
    ('sales_invoice',
     f'Sales invoice for Kumar Enterprises {RS}25000 on 1 Sept 2026',
     'customer_name', 'Kumar Enterprises', '2026-09-01'),

    ('sales_invoice',
     f'Create a sales invoice for ABC Traders & Co {RS}1,25,000 on 15 Aug 2026',
     'customer_name', 'ABC Traders', '2026-08-15'),

    ('purchase_bill',
     f'Purchase bill from Ramesh Suppliers {RS}18500 on 1 Sept 2026',
     'vendor_name', 'Ramesh Suppliers', '2026-09-01'),

    ('purchase_bill',
     f'Record purchase bill from Global Supplies Pvt Ltd {RS}45500 on 01/09/2026',
     'vendor_name', 'Global Supplies', '2026-09-01'),

    ('receipt',
     f'Receipt from Kumar Enterprises {RS}25000 in Cash on 1 Sept 2026',
     'party_ledger', 'Kumar Enterprises', '2026-09-01'),

    ('receipt',
     f'Money received from Raj Kumar & Sons {RS}75000 in HDFC Bank on 2026-09-01',
     'party_ledger', 'Raj Kumar', '2026-09-01'),

    ('payment',
     f'Payment to Ramesh Suppliers {RS}18500 from Bank on 1 Sept 2026',
     'party_ledger', 'Ramesh Suppliers', '2026-09-01'),

    ('payment',
     f'Paid {RS}12000 to Elite Office Supplies from Cash on 5 September 2026',
     'party_ledger', 'Elite Office Supplies', '2026-09-05'),

    ('journal',
     f'Journal entry debit Salary Payable credit Cash {RS}50000 on 1 Sept 2026',
     'dr_ledger', 'Salary Payable', '2026-09-01'),

    ('journal',
     f'JV debit Depreciation credit Fixed Assets {RS}5000 on 30 Sept 2026',
     'dr_ledger', 'Depreciation', '2026-09-30'),

    ('credit_note',
     f'Credit note for Kumar Enterprises {RS}5000 on 1 Sept 2026',
     'party_ledger', 'Kumar Enterprises', '2026-09-01'),

    ('credit_note',
     f'Sales return credit note for Zenith Corp {RS}8000 on 10 September 2026',
     'party_ledger', 'Zenith Corp', '2026-09-10'),

    ('debit_note',
     f'Debit note for Ramesh Suppliers {RS}3000 on 1 Sept 2026',
     'party_ledger', 'Ramesh Suppliers', '2026-09-01'),

    ('contra',
     f'Contra transfer {RS}10000 from Cash to HDFC Bank on 1 Sept 2026',
     'from_account', 'Cash', '2026-09-01'),

    # -- Contra with "Petty Cash" as ACCOUNT (must NOT route to custom_voucher) --
    ('contra',
     f'Bank transfer {RS}50000 from Petty Cash to SBI Current Account on 1 Sept 2026',
     'from_account', 'Petty Cash', '2026-09-01'),

    ('contra',
     f'Contra {RS}20000 from Petty Cash to HDFC Bank on 15 August 2026',
     'from_account', 'Petty Cash', '2026-08-15'),

    # ═══════════════════════════════════════════════════════════════════════════
    # STOCK TRANSACTIONS  (6 types)
    # ═══════════════════════════════════════════════════════════════════════════
    ('stock_journal',
     'Transfer 3 Laptop from Main Location to Chennai on 1 Sept 2026',
     'from_godown', 'Main Location', '2026-09-01'),

    ('stock_journal',
     'Transfer 10 Office Chair from Warehouse to Chennai Branch on 15 Aug 2026',
     'from_godown', 'Warehouse', '2026-08-15'),

    ('physical_stock',
     'Physical stock count 50 Remote at Main Location on 1 Sept 2026',
     'from_godown', 'Main Location', '2026-09-01'),

    ('physical_stock',
     'Stock count verification 100 Samsung Galaxy at Chennai on 2026-09-01',
     'from_godown', 'Chennai', '2026-09-01'),

    ('delivery_note',
     'Delivery Note for Kumar Enterprises 2 Samsung Galaxy from Main Location on 1 Sept 2026',
     'party_name', 'Kumar Enterprises', '2026-09-01'),

    ('delivery_note',
     'Delivery Note for Zenith Corp 5 Laptop from Warehouse on 1 September 2026',
     'party_name', 'Zenith Corp', '2026-09-01'),

    ('receipt_note',
     'Receipt Note from Kapoor Suppliers 5 Bed at Chennai on 1 Sept 2026',
     'party_name', 'Kapoor Suppliers', '2026-09-01'),

    ('receipt_note',
     'Goods received from Elite Suppliers 20 Bed at Main Location on 5 Sep 2026',
     'party_name', 'Elite Suppliers', '2026-09-05'),

    ('rejection_in',
     'Rejection In from Kumar Enterprises 3 Chair at Main Location on 1 Sept 2026',
     'party_name', 'Kumar Enterprises', '2026-09-01'),

    ('rejection_in',
     'Customer return goods rejection in from ABC Corp 10 Chair on 15 Aug 2026',
     'party_name', 'ABC Corp', '2026-08-15'),

    ('rejection_out',
     'Rejection Out to Ramesh Suppliers 2 Table from Main Location on 1 Sept 2026',
     'party_name', 'Ramesh Suppliers', '2026-09-01'),

    ('rejection_out',
     'Return to supplier rejection out to XYZ Vendors 5 Table on 1 Sept 2026',
     'party_name', 'XYZ Vendors', '2026-09-01'),

    # ═══════════════════════════════════════════════════════════════════════════
    # CUSTOM VOUCHER TYPES
    # -- Positive: text explicitly names a custom voucher type -----------------
    # ═══════════════════════════════════════════════════════════════════════════

    # GST Bill (custom type based on Sales in user's TallyPrime)
    ('custom_voucher',
     f'Create a GST Bill for Kumar Enterprises {RS}12000 on 1 Sept 2026',
     'voucher_type_name', 'GST Bill', '2026-09-01'),

    ('custom_voucher',
     f'Make a GST Bill for ABC Traders {RS}45000 on 15 August 2026',
     'voucher_type_name', 'GST Bill', '2026-08-15'),

    # Petty Cash (custom type based on Payment — used as VOUCHER TYPE, not account)
    ('custom_voucher',
     f'Create a Petty Cash entry {RS}500 on 1 Sept 2026',
     'voucher_type_name', 'Petty Cash', '2026-09-01'),

    ('custom_voucher',
     f'Record a Petty Cash voucher for office supplies {RS}350 on 1 Sept 2026',
     'voucher_type_name', 'Petty Cash', '2026-09-01'),

    # FP-Sales (another custom type in user's TallyPrime)
    ('custom_voucher',
     f'Create an FP-Sales for Zenith Corp {RS}75000 on 1 Sept 2026',
     'voucher_type_name', 'FP-Sales', '2026-09-01'),
    ('custom_voucher',
     f'Create an FP-Sales entry for Zenith Corp {RS}75000 on 1 Sept 2026',
     'voucher_type_name', 'FP-Sales', '2026-09-01'),

    # -- Negative: Petty Cash used as ACCOUNT name → must NOT be custom_voucher -
    # These must route to contra, not custom_voucher
    # (DemoEntityAgent has no DB, so _extract_custom_type won't fire for "from/to" pattern)
    ('contra',
     f'Transfer {RS}10000 from Petty Cash to Main Bank on 1 Sept 2026',
     'entity_type_self', 'contra', '2026-09-01'),

    # ═══════════════════════════════════════════════════════════════════════════
    # MASTER ENTITIES  (8 types)
    # ═══════════════════════════════════════════════════════════════════════════

    # -- GODOWN --
    ('godown', 'Add Godown Chennai',
     'name', 'Chennai', None),
    ('godown', 'Create warehouse Main Warehouse',
     'name', 'Main Warehouse', None),
    ('godown', 'Add Godown Chennai Branch under Main Location',
     'name', 'Chennai Branch', None),
    ('godown', 'Add Godown Chennai Branch under Main Location',
     'parent', 'Main Location', None),

    # -- UNIT --
    ('unit', 'Add unit Kilogram symbol Kg',
     'name', 'Kilogram', None),
    ('unit', 'Add unit Kilogram symbol Kg',
     'symbol', 'Kg', None),
    ('unit', 'Create unit of measure Nos',
     'name', 'Nos', None),
    ('unit', 'Add unit Pieces symbol Pcs decimal 2',
     'name', 'Pieces', None),
    ('unit', 'Add unit Pieces symbol Pcs decimal 2',
     'symbol', 'Pcs', None),

    # -- LEDGER --
    ('ledger', 'Add ledger HDFC Bank under Bank Accounts',
     'name', 'HDFC Bank', None),
    ('ledger', 'Add ledger HDFC Bank under Bank Accounts',
     'group', 'Bank Accounts', None),

    # -- GROUP --
    ('group', 'Add account group Electronics under Current Assets',
     'name', 'Electronics', None),
    ('group', 'Add account group Electronics under Current Assets',
     'parent', 'Current Assets', None),

    # -- CUSTOMER --
    ('customer',
     'Add customer Kumar Enterprises email kumar@example.com phone 9876543210',
     'name', 'Kumar Enterprises', None),
    ('customer',
     'Add customer Kumar Enterprises email kumar@example.com phone 9876543210',
     'email', 'kumar@example.com', None),

    # -- VENDOR --
    ('vendor',
     'Add vendor Ramesh Suppliers phone 9876543210 GST 27AABCU9603R1ZX',
     'name', 'Ramesh Suppliers', None),
    ('vendor',
     'Add vendor Ramesh Suppliers phone 9876543210 GST 27AABCU9603R1ZX',
     'gstin', '27AABCU9603R1ZX', None),

    # -- STOCK ITEM --
    ('stock_item', f'Add stock item Samsung Galaxy unit Nos rate 25000',
     'name', 'Samsung Galaxy', None),
    ('stock_item', f'Add stock item Samsung Galaxy unit Nos rate 25000',
     'unit', 'Nos', None),
    ('stock_item', f'Add stock item Samsung Galaxy unit Nos rate 25000',
     'rate', '25000', None),
    ('stock_item',
     'Add product Office Chair group Furniture unit Nos rate 5000 opening qty 10',
     'name', 'Office Chair', None),
    ('stock_item',
     'Add product Office Chair group Furniture unit Nos rate 5000 opening qty 10',
     'opening_qty', '10', None),

    # -- STOCK GROUP --
    ('stock_group', 'Add stock group Electronics under Primary',
     'name', 'Electronics', None),
    ('stock_group', 'Create item group Furniture',
     'name', 'Furniture', None),
]


# -----------------------------------------------------------------------------
# Runner
# -----------------------------------------------------------------------------

SECTIONS = {
    'sales_invoice': 'ACCOUNTING VOUCHERS', 'purchase_bill': 'ACCOUNTING VOUCHERS',
    'receipt':       'ACCOUNTING VOUCHERS', 'payment':       'ACCOUNTING VOUCHERS',
    'journal':       'ACCOUNTING VOUCHERS', 'credit_note':   'ACCOUNTING VOUCHERS',
    'debit_note':    'ACCOUNTING VOUCHERS', 'contra':        'ACCOUNTING VOUCHERS',
    'stock_journal': 'STOCK TRANSACTIONS',  'physical_stock':'STOCK TRANSACTIONS',
    'delivery_note': 'STOCK TRANSACTIONS',  'receipt_note':  'STOCK TRANSACTIONS',
    'rejection_in':  'STOCK TRANSACTIONS',  'rejection_out': 'STOCK TRANSACTIONS',
    'custom_voucher':'CUSTOM VOUCHERS',
    'godown':        'MASTER ENTITIES',     'unit':          'MASTER ENTITIES',
    'ledger':        'MASTER ENTITIES',     'group':         'MASTER ENTITIES',
    'customer':      'MASTER ENTITIES',     'vendor':        'MASTER ENTITIES',
    'stock_item':    'MASTER ENTITIES',     'stock_group':   'MASTER ENTITIES',
}

passed = failed = 0
current_section = ''

for exp_type, text, key, exp_val, exp_date in TESTS:
    r = a.extract(text)
    d = r['data']
    et = r['entity_type']
    date = d.get('date', '')

    # Special key 'entity_type_self' checks the entity_type itself
    if key == 'entity_type_self':
        val = et
    else:
        val = str(d.get(key, ''))

    type_ok = et == exp_type
    val_ok  = exp_val.lower() in val.lower()
    date_ok = (exp_date is None) or (date == exp_date)
    ok = type_ok and val_ok and date_ok

    sec = SECTIONS.get(exp_type, 'OTHER')
    if sec != current_section:
        current_section = sec
        print(f'\n  {"-" * 56}')
        print(f'  {sec}')
        print(f'  {"-" * 56}')

    status = 'PASS' if ok else 'FAIL'
    if ok:
        passed += 1
    else:
        failed += 1

    date_str = f'  date={date}' if exp_date else ''
    print(f'  {status}  {et:18s}{date_str}')
    print(f'        {key} = {val[:50]}')
    if not ok:
        if not type_ok:  print(f'        !! TYPE  expected={exp_type!r}  got={et!r}')
        if not val_ok:   print(f'        !! VALUE expected~={exp_val!r}  got={val!r}')
        if not date_ok:  print(f'        !! DATE  expected={exp_date!r}  got={date!r}')
    print(f'        "{text[:70]}"')

print(f'\n{"=" * 60}')
print(f'  TOTAL: {passed} PASSED   {failed} FAILED   out of {passed + failed}')
print(f'{"=" * 60}')

sys.exit(0 if failed == 0 else 1)
