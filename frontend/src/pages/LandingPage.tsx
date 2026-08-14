import { Link } from 'react-router-dom';
import {
  MessageSquare, BarChart3, CheckSquare, Upload, FileBarChart,
  Shield, Zap, ArrowRight, Star, ChevronRight,
  Brain, Globe, Lock
} from 'lucide-react';
import { Button } from '../components/ui/button';
import { FinPilotLogo } from '../components/ui/FinPilotLogo';

const features = [
  {
    icon: Brain,
    title: 'AI Financial Assistant',
    description: 'Ask natural language questions about your finances. Get instant insights, summaries, and actionable recommendations powered by advanced AI.',
    gradient: 'from-indigo-500 to-violet-600',
  },
  {
    icon: BarChart3,
    title: 'Advanced Analytics',
    description: 'Beautiful, interactive charts and dashboards. Track revenue, expenses, profit margins, and customer metrics in real time.',
    gradient: 'from-blue-500 to-cyan-600',
  },
  {
    icon: CheckSquare,
    title: 'Approval Workflows',
    description: 'Multi-level transaction approval with role-based access. Ensure every payment and invoice gets proper review before processing.',
    gradient: 'from-violet-500 to-purple-600',
  },
  {
    icon: Upload,
    title: 'Bulk Data Import',
    description: 'Upload CSV files for customers, vendors, products, invoices, and expenses. AI validates data and flags errors automatically.',
    gradient: 'from-emerald-500 to-teal-600',
  },
  {
    icon: FileBarChart,
    title: 'Professional Reports',
    description: 'Generate P&L, revenue, expense, and receivables reports in one click. Export as PDF with your company branding.',
    gradient: 'from-orange-500 to-amber-600',
  },
  {
    icon: Zap,
    title: 'Tally Integration',
    description: 'Seamlessly sync your data with Tally ERP. Push invoices, expenses, and payments without manual data entry.',
    gradient: 'from-pink-500 to-rose-600',
  },
];

const stats = [
  { value: '10x', label: 'Faster Reconciliation' },
  { value: '99.9%', label: 'Data Accuracy' },
  { value: '40%', label: 'Time Saved' },
  { value: '500+', label: 'Companies Trust Us' },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Navbar */}
      <nav className="fixed top-0 inset-x-0 z-50 border-b border-white/10 bg-slate-950/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-2">
              <FinPilotLogo size={32} />
              <span className="text-xl font-bold">FinPilot AI</span>
            </div>
            <div className="flex items-center gap-3">
              <Link to="/login">
                <Button variant="ghost" className="text-white hover:bg-white/10 hover:text-white">
                  Login
                </Button>
              </Link>
              <Link to="/signup">
                <Button className="bg-indigo-600 hover:bg-indigo-700 text-white">
                  Get Started
                  <ArrowRight className="ml-2 w-4 h-4" />
                </Button>
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-32 pb-24 overflow-hidden">
        {/* Background gradients */}
        <div className="absolute inset-0 overflow-hidden">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[500px] bg-indigo-600/20 rounded-full blur-3xl" />
          <div className="absolute top-20 right-0 w-[400px] h-[400px] bg-violet-600/15 rounded-full blur-3xl" />
          <div className="absolute bottom-0 left-0 w-[400px] h-[400px] bg-blue-600/10 rounded-full blur-3xl" />
        </div>

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-sm font-medium mb-8">
            <Star className="w-3.5 h-3.5" />
            AI-Powered Finance Platform
          </div>

          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-extrabold leading-tight mb-6">
            <span className="text-white">AI-powered finance</span>
            <br />
            <span className="bg-gradient-to-r from-indigo-400 via-violet-400 to-pink-400 bg-clip-text text-transparent">
              operations, built for
            </span>
            <br />
            <span className="text-white">accuracy.</span>
          </h1>

          <p className="text-xl text-slate-400 max-w-2xl mx-auto mb-10 leading-relaxed">
            Automate your accounts, get AI-driven insights, manage invoices and expenses —
            all in one platform designed for modern Indian businesses.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link to="/signup">
              <Button size="xl" className="bg-indigo-600 hover:bg-indigo-700 text-white w-full sm:w-auto group">
                Start Free Trial
                <ArrowRight className="ml-2 w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </Button>
            </Link>
            <Link to="/login">
              <Button size="xl" variant="outline" className="border-white/20 text-white hover:bg-white/10 hover:text-white w-full sm:w-auto bg-transparent">
                View Demo
              </Button>
            </Link>
          </div>

          {/* Stats */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8 mt-20 max-w-3xl mx-auto">
            {stats.map((stat) => (
              <div key={stat.label} className="text-center">
                <div className="text-3xl font-bold bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent">{stat.value}</div>
                <div className="text-sm text-slate-500 mt-1">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section className="py-24 relative">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-4xl font-bold text-white mb-4">
              Everything you need to run your finances
            </h2>
            <p className="text-lg text-slate-400 max-w-2xl mx-auto">
              A complete suite of AI-powered tools for modern financial operations
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((feature) => {
              const Icon = feature.icon;
              return (
                <div
                  key={feature.title}
                  className="group relative bg-slate-900 border border-white/10 rounded-2xl p-6 hover:border-indigo-500/50 transition-all duration-300 hover:shadow-xl hover:shadow-indigo-500/10"
                >
                  <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${feature.gradient} flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
                    <Icon className="w-6 h-6 text-white" />
                  </div>
                  <h3 className="text-lg font-semibold text-white mb-2">{feature.title}</h3>
                  <p className="text-slate-400 text-sm leading-relaxed">{feature.description}</p>
                  <div className="mt-4 flex items-center gap-1 text-indigo-400 text-sm font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                    Learn more <ChevronRight className="w-4 h-4" />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* Dashboard Preview Section */}
      <section className="py-24 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-indigo-950/30 to-transparent" />
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-16 items-center">
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium mb-6">
                <Globe className="w-3 h-3" />
                Built for Indian Businesses
              </div>
              <h2 className="text-4xl font-bold text-white mb-6">
                INR-first, GST-ready, Tally-compatible
              </h2>
              <p className="text-slate-400 text-lg mb-8 leading-relaxed">
                FinPilot AI is built from the ground up for Indian businesses.
                Native INR support with lakhs/crores formatting, GST-compliant invoicing,
                and seamless Tally integration.
              </p>
              <ul className="space-y-4">
                {[
                  'Indian number formatting (Lakhs & Crores)',
                  'GST-compliant invoice generation',
                  'Tally ERP synchronization',
                  'Multi-currency support',
                ].map((item) => (
                  <li key={item} className="flex items-center gap-3 text-slate-300">
                    <div className="w-5 h-5 rounded-full bg-indigo-600 flex items-center justify-center shrink-0">
                      <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
            <div className="relative">
              <div className="bg-slate-900 border border-white/10 rounded-2xl p-6 shadow-2xl">
                <div className="grid grid-cols-2 gap-4 mb-6">
                  {[
                    { label: 'Total Revenue', value: '₹24.5L', change: '+12.3%', color: 'text-emerald-400' },
                    { label: 'Net Profit', value: '₹8.2L', change: '+8.1%', color: 'text-emerald-400' },
                    { label: 'Expenses', value: '₹16.3L', change: '+3.2%', color: 'text-red-400' },
                    { label: 'Outstanding', value: '₹5.8L', change: '-2.1%', color: 'text-emerald-400' },
                  ].map((kpi) => (
                    <div key={kpi.label} className="bg-slate-800 rounded-xl p-4">
                      <p className="text-slate-500 text-xs">{kpi.label}</p>
                      <p className="text-white font-bold text-xl mt-1">{kpi.value}</p>
                      <p className={`text-xs mt-1 ${kpi.color}`}>{kpi.change}</p>
                    </div>
                  ))}
                </div>
                <div className="bg-slate-800 rounded-xl p-4">
                  <p className="text-slate-400 text-xs mb-3">Monthly Revenue</p>
                  <div className="flex items-end gap-2 h-24">
                    {[40, 65, 50, 80, 70, 90, 75, 95, 85, 100, 88, 92].map((h, i) => (
                      <div
                        key={i}
                        className="flex-1 bg-gradient-to-t from-indigo-600 to-violet-500 rounded-sm opacity-80 hover:opacity-100 transition-opacity"
                        style={{ height: `${h}%` }}
                      />
                    ))}
                  </div>
                  <div className="flex justify-between mt-2 text-slate-600 text-xs">
                    <span>Jan</span><span>Jun</span><span>Dec</span>
                  </div>
                </div>
              </div>
              {/* Floating badge */}
              <div className="absolute -top-4 -right-4 bg-emerald-500 text-white text-xs font-semibold px-3 py-1.5 rounded-full shadow-lg">
                AI-powered insights
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Security Section */}
      <section className="py-24">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="bg-gradient-to-br from-slate-900 to-indigo-950 border border-white/10 rounded-3xl p-12 text-center relative overflow-hidden">
            <div className="absolute inset-0 overflow-hidden">
              <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-600/10 rounded-full blur-3xl" />
              <div className="absolute bottom-0 left-0 w-64 h-64 bg-violet-600/10 rounded-full blur-3xl" />
            </div>
            <div className="relative">
              <div className="w-14 h-14 rounded-2xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center mx-auto mb-6">
                <Lock className="w-7 h-7 text-indigo-400" />
              </div>
              <h2 className="text-3xl font-bold text-white mb-4">Enterprise-grade Security</h2>
              <p className="text-slate-400 max-w-xl mx-auto mb-8">
                Your financial data is protected with JWT authentication, role-based access control,
                end-to-end encryption, and comprehensive audit logs.
              </p>
              <div className="flex flex-wrap justify-center gap-4">
                {['JWT Auth', 'Role-based Access', 'Audit Logs', 'Data Encryption'].map((item) => (
                  <span key={item} className="px-4 py-2 rounded-full bg-slate-800 border border-white/10 text-slate-300 text-sm">
                    {item}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-24">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="text-5xl font-bold text-white mb-6">
            Ready to transform your
            <span className="bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent"> finance operations?</span>
          </h2>
          <p className="text-xl text-slate-400 mb-10">
            Join hundreds of businesses using FinPilot AI to save time, reduce errors, and grow faster.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link to="/signup">
              <Button size="xl" className="bg-indigo-600 hover:bg-indigo-700 text-white w-full sm:w-auto group">
                Get started for free
                <ArrowRight className="ml-2 w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/10 py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <FinPilotLogo size={28} />
              <span className="font-bold text-white">FinPilot AI</span>
            </div>
            <p className="text-slate-500 text-sm">
              © 2024 FinPilot AI. AI-powered finance operations for Indian businesses.
            </p>
            <div className="flex gap-6 text-slate-500 text-sm">
              <span className="hover:text-slate-300 cursor-pointer">Privacy</span>
              <span className="hover:text-slate-300 cursor-pointer">Terms</span>
              <span className="hover:text-slate-300 cursor-pointer">Contact</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
