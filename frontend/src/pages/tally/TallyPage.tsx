import { useState } from 'react';
import { Zap, CheckCircle, XCircle, RefreshCw, Settings, Info, ArrowRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Switch } from '../../components/ui/switch';
import { Badge } from '../../components/ui/badge';
import { Separator } from '../../components/ui/separator';
import { toast } from '../../components/ui/use-toast';

export default function TallyPage() {
  const [isConnected, setIsConnected] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [host, setHost] = useState('localhost');
  const [port, setPort] = useState('9000');
  const [autoSync, setAutoSync] = useState(false);

  const handleConnect = async () => {
    setIsSyncing(true);
    await new Promise(r => setTimeout(r, 2000));
    setIsSyncing(false);
    // In real implementation, would test connection
    toast({
      title: 'Connection test complete',
      description: 'Make sure Tally is running with TallyPrime and the connector service is enabled.',
      variant: 'default',
    });
  };

  const handleSync = async () => {
    setIsSyncing(true);
    await new Promise(r => setTimeout(r, 3000));
    setIsSyncing(false);
    toast({ title: 'Sync initiated', description: 'Data sync with Tally has been started.', variant: 'success' });
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Tally Integration</h2>
        <p className="text-sm text-slate-500">Connect and sync data with Tally ERP</p>
      </div>

      {/* Status Card */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${isConnected ? 'bg-emerald-100' : 'bg-slate-100'}`}>
                <Zap className={`w-6 h-6 ${isConnected ? 'text-emerald-600' : 'text-slate-400'}`} />
              </div>
              <div>
                <p className="font-semibold text-slate-900">Tally Connection Status</p>
                <div className="flex items-center gap-2 mt-1">
                  {isConnected ? (
                    <>
                      <CheckCircle className="w-4 h-4 text-emerald-500" />
                      <span className="text-sm text-emerald-600 font-medium">Connected</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="w-4 h-4 text-slate-400" />
                      <span className="text-sm text-slate-500">Not connected</span>
                    </>
                  )}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-3">
              {isConnected && (
                <Button onClick={handleSync} loading={isSyncing} variant="outline">
                  <RefreshCw className={`w-4 h-4 mr-2 ${isSyncing ? 'animate-spin' : ''}`} />
                  Sync Now
                </Button>
              )}
              <Button onClick={() => setIsConnected(!isConnected)} variant={isConnected ? 'destructive' : 'default'}>
                {isConnected ? 'Disconnect' : 'Connect'}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Configuration */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Settings className="w-4 h-4 text-indigo-600" />
            Connection Settings
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Tally Host</Label>
              <Input value={host} onChange={e => setHost(e.target.value)} placeholder="localhost" />
            </div>
            <div className="space-y-1.5">
              <Label>Port</Label>
              <Input value={port} onChange={e => setPort(e.target.value)} placeholder="9000" />
            </div>
          </div>
          <div className="flex items-center justify-between p-4 bg-slate-50 rounded-lg">
            <div>
              <p className="font-medium text-slate-900 text-sm">Auto Sync</p>
              <p className="text-xs text-slate-500">Automatically sync data every hour</p>
            </div>
            <Switch checked={autoSync} onCheckedChange={setAutoSync} />
          </div>
          <Button onClick={handleConnect} loading={isSyncing} variant="outline">
            Test Connection
          </Button>
        </CardContent>
      </Card>

      {/* Sync Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Sync Configuration</CardTitle>
          <CardDescription>Choose what data to sync with Tally</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {[
            { label: 'Sales Invoices', description: 'Sync sales invoices to Tally ledger', enabled: true },
            { label: 'Purchase Invoices', description: 'Sync vendor invoices and expenses', enabled: true },
            { label: 'Payments', description: 'Sync payment vouchers', enabled: false },
            { label: 'Customer Masters', description: 'Sync customer/party ledgers', enabled: true },
            { label: 'Vendor Masters', description: 'Sync vendor/party ledgers', enabled: true },
            { label: 'Stock Items', description: 'Sync inventory items', enabled: false },
          ].map((item) => (
            <div key={item.label} className="flex items-center justify-between py-2">
              <div>
                <p className="text-sm font-medium text-slate-900">{item.label}</p>
                <p className="text-xs text-slate-500">{item.description}</p>
              </div>
              <Switch defaultChecked={item.enabled} />
            </div>
          ))}
        </CardContent>
      </Card>

      {/* How it works */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Info className="w-4 h-4 text-indigo-600" />
            How Tally Integration Works
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4 text-sm text-slate-600">
            <p>FinPilot AI connects to Tally via the <strong className="text-slate-900">TallyPrime Connector API</strong> (HTTP/XML interface).</p>

            <div className="space-y-3">
              {[
                { step: '1', title: 'Install TallyPrime', desc: 'Ensure Tally Prime 2.x or higher is installed on your system' },
                { step: '2', title: 'Enable Tally Connector', desc: 'In Tally, go to F12 > Configure > Connectivity and enable the HTTP server on port 9000' },
                { step: '3', title: 'Configure Connection', desc: 'Enter the host and port above (usually localhost:9000 if running on same machine)' },
                { step: '4', title: 'Test & Connect', desc: 'Click "Test Connection" to verify, then "Connect" to start syncing' },
              ].map((item) => (
                <div key={item.step} className="flex gap-3">
                  <div className="w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-xs font-bold shrink-0">
                    {item.step}
                  </div>
                  <div>
                    <p className="font-medium text-slate-900">{item.title}</p>
                    <p className="text-slate-500">{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg">
              <p className="text-amber-800 text-xs">
                <strong>Note:</strong> Tally must be running and the company file must be open for sync to work.
                The integration uses XML-based TDL (Tally Definition Language) requests.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
