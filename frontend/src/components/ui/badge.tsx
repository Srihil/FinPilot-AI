import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "../../utils/cn"

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-indigo-100 text-indigo-800",
        secondary: "border-transparent bg-yellow-100 text-yellow-800",
        destructive: "border-transparent bg-red-100 text-red-800",
        outline: "border-slate-300 text-slate-600",
        success: "border-transparent bg-emerald-100 text-emerald-800",
        blue: "border-transparent bg-blue-100 text-blue-800",
        purple: "border-transparent bg-purple-100 text-purple-800",
        gray: "border-transparent bg-slate-100 text-slate-700",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

function StatusBadge({ status }: { status?: string | null }) {
  if (!status) return null;
  const getVariant = (s: string): VariantProps<typeof badgeVariants>['variant'] => {
    switch (s?.toUpperCase()) {
      case 'PAID': case 'APPROVED': case 'ACTIVE': case 'SUCCESS': return 'success';
      case 'PENDING_APPROVAL': case 'PENDING': return 'secondary';
      case 'DRAFT': return 'gray';
      case 'OVERDUE': case 'CANCELLED': case 'FAILED': case 'INACTIVE': return 'destructive';
      case 'INVOICE': return 'blue';
      case 'EXPENSE': return 'purple';
      default: return 'outline';
    }
  };

  const getLabel = (s: string) => {
    switch (s?.toUpperCase()) {
      case 'PENDING_APPROVAL': return 'Pending Approval';
      default: return s?.charAt(0) + s?.slice(1)?.toLowerCase().replace(/_/g, ' ');
    }
  };

  return (
    <Badge variant={getVariant(status)}>
      {getLabel(status)}
    </Badge>
  );
}

export { Badge, badgeVariants, StatusBadge }
