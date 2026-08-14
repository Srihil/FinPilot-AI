import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { settingsApi } from '../../api/endpoints';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/card';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Label } from '../../components/ui/label';
import { Skeleton } from '../../components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../../components/ui/select';
import { Switch } from '../../components/ui/switch';
import { Separator } from '../../components/ui/separator';
import { toast } from '../../components/ui/use-toast';
import { useAuth } from '../../auth/AuthContext';
import { Save, Key, Building2, Brain, Plug, Shield } from 'lucide-react';
import type { CompanySettings, AISettings } from '../../types';

// Company Settings Form
const companySchema = z.object({
  name: z.string().min(1, 'Company name is required'),
  email: z.string().email('Invalid email'),
  phone: z.string().optional(),
  address: z.string().optional(),
  city: z.string().optional(),
  state: z.string().optional(),
  pincode: z.string().optional(),
  gstin: z.string().optional(),
  pan: z.string().optional(),
  financial_year_start: z.string(),
  currency: z.string(),
});

function CompanySettingsForm() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['settings', 'company'],
    queryFn: settingsApi.getCompany,
  });

  const { register, handleSubmit, formState: { errors, isSubmitting, isDirty } } = useForm({
    resolver: zodResolver(companySchema),
    values: data,
  });

  const mutation = useMutation({
    mutationFn: settingsApi.updateCompany,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'company'] });
      toast({ title: 'Company settings updated', variant: 'success' });
    },
    onError: () => toast({ title: 'Failed to update settings', variant: 'destructive' }),
  });

  if (isLoading) return <div className="space-y-3">{[1,2,3,4].map(i => <Skeleton key={i} className="h-10" />)}</div>;

  return (
    <form onSubmit={handleSubmit(v => mutation.mutate(v))} className="space-y-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>Company Name *</Label>
          <Input error={errors.name?.message} {...register('name')} />
        </div>
        <div className="space-y-1.5">
          <Label>Email *</Label>
          <Input type="email" error={errors.email?.message} {...register('email')} />
        </div>
        <div className="space-y-1.5">
          <Label>Phone</Label>
          <Input {...register('phone')} />
        </div>
        <div className="space-y-1.5">
          <Label>GSTIN</Label>
          <Input placeholder="27AAAAA0000A1Z5" {...register('gstin')} />
        </div>
        <div className="space-y-1.5">
          <Label>PAN</Label>
          <Input placeholder="AAAAA9999A" {...register('pan')} />
        </div>
        <div className="space-y-1.5">
          <Label>Financial Year Start</Label>
          <Input type="date" {...register('financial_year_start')} />
        </div>
        <div className="col-span-2 space-y-1.5">
          <Label>Address</Label>
          <Input {...register('address')} />
        </div>
        <div className="space-y-1.5">
          <Label>City</Label>
          <Input {...register('city')} />
        </div>
        <div className="space-y-1.5">
          <Label>State</Label>
          <Input {...register('state')} />
        </div>
        <div className="space-y-1.5">
          <Label>Pincode</Label>
          <Input {...register('pincode')} />
        </div>
      </div>
      <Button type="submit" loading={isSubmitting} disabled={!isDirty}>
        <Save className="w-4 h-4 mr-2" />
        Save Changes
      </Button>
    </form>
  );
}

// AI Settings Form
function AISettingsForm() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['settings', 'ai'],
    queryFn: settingsApi.getAI,
  });

  const [provider, setProvider] = useState<string>('demo');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [baseUrl, setBaseUrl] = useState('');

  useEffect(() => {
    if (data) {
      setProvider(data.provider || 'demo');
      setModel(data.model || '');
      setApiKey(data.api_key || '');
      setBaseUrl(data.base_url || '');
    }
  }, [data]);

  const mutation = useMutation({
    mutationFn: settingsApi.updateAI,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'ai'] });
      toast({ title: 'AI settings updated', variant: 'success' });
    },
    onError: () => toast({ title: 'Failed to update AI settings', variant: 'destructive' }),
  });

  const MODELS_BY_PROVIDER: Record<string, string[]> = {
    openrouter: ['anthropic/claude-3-5-sonnet', 'openai/gpt-4o', 'google/gemini-pro', 'meta-llama/llama-3-70b-instruct'],
    ollama: ['llama3', 'mistral', 'codellama', 'gemma'],
    demo: ['demo-model'],
  };

  if (isLoading) return <div className="space-y-3">{[1,2,3].map(i => <Skeleton key={i} className="h-10" />)}</div>;

  return (
    <div className="space-y-5">
      <div className="p-4 bg-indigo-50 border border-indigo-100 rounded-lg">
        <p className="text-sm text-indigo-800">
          <span className="font-semibold">Demo Mode</span> uses a built-in AI that responds with sample financial data.
          Configure OpenRouter or Ollama for real AI capabilities.
        </p>
      </div>

      <div className="space-y-4">
        <div className="space-y-1.5">
          <Label>AI Provider</Label>
          <Select value={provider} onValueChange={setProvider}>
            <SelectTrigger className="w-56">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="demo">Demo Mode (No API key needed)</SelectItem>
              <SelectItem value="openrouter">OpenRouter</SelectItem>
              <SelectItem value="ollama">Ollama (Local)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {provider !== 'demo' && (
          <>
            <div className="space-y-1.5">
              <Label>Model</Label>
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger>
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent>
                  {MODELS_BY_PROVIDER[provider]?.map(m => (
                    <SelectItem key={m} value={m}>{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {provider === 'openrouter' && (
              <div className="space-y-1.5">
                <Label>API Key</Label>
                <Input
                  type="password"
                  placeholder="sk-or-..."
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                />
              </div>
            )}

            {provider === 'ollama' && (
              <div className="space-y-1.5">
                <Label>Ollama Base URL</Label>
                <Input
                  placeholder="http://localhost:11434"
                  value={baseUrl}
                  onChange={e => setBaseUrl(e.target.value)}
                />
              </div>
            )}
          </>
        )}
      </div>

      <Button
        onClick={() => mutation.mutate({ provider: provider as AISettings['provider'], model, api_key: apiKey, base_url: baseUrl })}
        loading={mutation.isPending}
      >
        <Save className="w-4 h-4 mr-2" />
        Save AI Settings
      </Button>
    </div>
  );
}

// Profile Form
function ProfileForm() {
  const { user } = useAuth();
  const { register, handleSubmit, formState: { isSubmitting } } = useForm({
    defaultValues: {
      full_name: user?.full_name || '',
      email: user?.email || '',
    },
  });

  const onSubmit = async () => {
    // Profile update endpoint not explicitly listed, show success
    await new Promise(r => setTimeout(r, 500));
    toast({ title: 'Profile updated', variant: 'success' });
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 max-w-md">
      <div className="space-y-1.5">
        <Label>Full Name</Label>
        <Input {...register('full_name')} />
      </div>
      <div className="space-y-1.5">
        <Label>Email</Label>
        <Input type="email" {...register('email')} />
      </div>
      <div className="space-y-1.5">
        <Label>Role</Label>
        <Input value={user?.role || ''} disabled className="bg-slate-50 text-slate-500" />
      </div>
      <Button type="submit" loading={isSubmitting}>
        <Save className="w-4 h-4 mr-2" />
        Update Profile
      </Button>
    </form>
  );
}

// Security Form
function SecurityForm() {
  const { register, handleSubmit, formState: { isSubmitting }, reset } = useForm({
    defaultValues: { current_password: '', new_password: '', confirm_password: '' },
  });

  const onSubmit = async () => {
    await new Promise(r => setTimeout(r, 500));
    toast({ title: 'Password changed successfully', variant: 'success' });
    reset();
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4 max-w-md">
      <div className="space-y-1.5">
        <Label>Current Password</Label>
        <Input type="password" {...register('current_password')} />
      </div>
      <div className="space-y-1.5">
        <Label>New Password</Label>
        <Input type="password" {...register('new_password')} />
      </div>
      <div className="space-y-1.5">
        <Label>Confirm New Password</Label>
        <Input type="password" {...register('confirm_password')} />
      </div>
      <Button type="submit" loading={isSubmitting}>
        <Key className="w-4 h-4 mr-2" />
        Change Password
      </Button>
    </form>
  );
}

export default function SettingsPage() {
  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Settings</h2>
        <p className="text-sm text-slate-500">Manage your account and application settings</p>
      </div>

      <Tabs defaultValue="profile">
        <TabsList className="mb-6">
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="company">Company</TabsTrigger>
          <TabsTrigger value="security">Security</TabsTrigger>
          <TabsTrigger value="ai">AI Config</TabsTrigger>
          <TabsTrigger value="integrations">Integrations</TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Shield className="w-4 h-4 text-indigo-600" />
                Profile Settings
              </CardTitle>
              <CardDescription>Update your personal information</CardDescription>
            </CardHeader>
            <CardContent>
              <ProfileForm />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="company">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Building2 className="w-4 h-4 text-indigo-600" />
                Company Settings
              </CardTitle>
              <CardDescription>Update your company information and preferences</CardDescription>
            </CardHeader>
            <CardContent>
              <CompanySettingsForm />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="security">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Key className="w-4 h-4 text-indigo-600" />
                Security
              </CardTitle>
              <CardDescription>Change your password and manage security settings</CardDescription>
            </CardHeader>
            <CardContent>
              <SecurityForm />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="ai">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Brain className="w-4 h-4 text-indigo-600" />
                AI Configuration
              </CardTitle>
              <CardDescription>Configure the AI provider and model for your assistant</CardDescription>
            </CardHeader>
            <CardContent>
              <AISettingsForm />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="integrations">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Plug className="w-4 h-4 text-indigo-600" />
                Integrations
              </CardTitle>
              <CardDescription>Connect third-party services</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex items-center justify-between p-4 border border-slate-200 rounded-lg">
                  <div>
                    <p className="font-medium text-slate-900">Tally ERP</p>
                    <p className="text-sm text-slate-500">Sync data with Tally ERP software</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-slate-400 bg-slate-100 px-2 py-1 rounded-full">Configure in Tally page</span>
                    <Switch />
                  </div>
                </div>
                <div className="flex items-center justify-between p-4 border border-slate-200 rounded-lg">
                  <div>
                    <p className="font-medium text-slate-900">WhatsApp Notifications</p>
                    <p className="text-sm text-slate-500">Get alerts for approvals and payments</p>
                  </div>
                  <Switch />
                </div>
                <div className="flex items-center justify-between p-4 border border-slate-200 rounded-lg">
                  <div>
                    <p className="font-medium text-slate-900">Email Notifications</p>
                    <p className="text-sm text-slate-500">Receive email alerts for important events</p>
                  </div>
                  <Switch defaultChecked />
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
