import { useNavigate } from 'react-router-dom';
import { Receipt, Wand2 } from 'lucide-react';
import { Button } from '../../components/ui/button';
import { Card, CardContent } from '../../components/ui/card';

const VOUCHER_TYPES = [
  {
    name: 'Sales',
    shortcut: 'F8',
    color: 'bg-green-50 border-green-200',
    badge: 'bg-green-100 text-green-700',
    description: 'Record a sale to a customer. Money owed to you.',
    example: 'Sold ₹50,000 of goods to Rahul Enterprises',
    aiPrompt: 'Create a sales voucher',
  },
  {
    name: 'Purchase',
    shortcut: 'F9',
    color: 'bg-orange-50 border-orange-200',
    badge: 'bg-orange-100 text-orange-700',
    description: 'Record a purchase from a supplier. Money you owe.',
    example: 'Bought ₹30,000 of raw material from XYZ Traders',
    aiPrompt: 'Create a purchase voucher',
  },
  {
    name: 'Receipt',
    shortcut: 'F6',
    color: 'bg-blue-50 border-blue-200',
    badge: 'bg-blue-100 text-blue-700',
    description: 'Money received into your bank or cash from a customer.',
    example: 'Received ₹50,000 from Rahul Enterprises by NEFT',
    aiPrompt: 'Create a receipt voucher',
  },
  {
    name: 'Payment',
    shortcut: 'F5',
    color: 'bg-red-50 border-red-200',
    badge: 'bg-red-100 text-red-700',
    description: 'Money paid out from your bank or cash — to a supplier or for any expense.',
    example: 'Paid ₹15,000 office rent by cash / paid electricity bill ₹3,200',
    aiPrompt: 'Create a payment voucher',
  },
  {
    name: 'Journal',
    shortcut: 'F7',
    color: 'bg-purple-50 border-purple-200',
    badge: 'bg-purple-100 text-purple-700',
    description: 'Internal accounting adjustment — no cash moves, just entries between ledgers.',
    example: 'Depreciation entry, GST adjustment, interest accrual',
    aiPrompt: 'Create a journal voucher',
  },
  {
    name: 'Contra',
    shortcut: 'F4',
    color: 'bg-slate-50 border-slate-200',
    badge: 'bg-slate-100 text-slate-700',
    description: 'Transfer between your own cash and bank accounts only.',
    example: 'Deposited ₹10,000 cash into HDFC Bank',
    aiPrompt: 'Create a contra voucher',
  },
  {
    name: 'Credit Note',
    shortcut: 'Ctrl+F8',
    color: 'bg-cyan-50 border-cyan-200',
    badge: 'bg-cyan-100 text-cyan-700',
    description: 'Sales return — customer sent goods back, reverse the original sale.',
    example: 'Rahul Enterprises returned ₹5,000 of damaged goods',
    aiPrompt: 'Create a credit note',
  },
  {
    name: 'Debit Note',
    shortcut: 'Ctrl+F9',
    color: 'bg-yellow-50 border-yellow-200',
    badge: 'bg-yellow-100 text-yellow-700',
    description: 'Purchase return — you sent goods back to supplier, reverse the purchase.',
    example: 'Returned ₹3,000 of defective material to XYZ Traders',
    aiPrompt: 'Create a debit note',
  },
];

export default function VoucherTypesPage() {
  const navigate = useNavigate();

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <Receipt className="w-6 h-6 text-indigo-600" />
          Voucher Types
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">
          TallyPrime voucher types — select one to create a voucher using AI
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        {VOUCHER_TYPES.map(vt => (
          <Card key={vt.name} className={`border ${vt.color} hover:shadow-md transition-shadow`}>
            <CardContent className="p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-slate-900 text-base">{vt.name}</h3>
                <span className={`text-xs font-mono font-medium px-2 py-0.5 rounded ${vt.badge}`}>
                  {vt.shortcut}
                </span>
              </div>
              <p className="text-sm text-slate-600">{vt.description}</p>
              <div className="bg-white/60 rounded p-2.5">
                <p className="text-xs text-slate-500 font-medium mb-0.5">Example</p>
                <p className="text-xs text-slate-700 italic">{vt.example}</p>
              </div>
              <Button
                size="sm"
                className="w-full gap-2"
                onClick={() => navigate('/ai-create', { state: { prompt: vt.aiPrompt } })}
              >
                <Wand2 className="w-3.5 h-3.5" />
                Create with AI
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-4 text-sm text-indigo-700">
        <p className="font-medium mb-1">How it works</p>
        <p>Click <strong>Create with AI</strong> on any voucher type above. The AI will ask you for the details (party name, amount, date) and automatically create the voucher in both FinPilot and TallyPrime.</p>
      </div>
    </div>
  );
}
