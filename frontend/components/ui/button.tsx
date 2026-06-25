import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex h-9 shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius)] px-3 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:pointer-events-none disabled:opacity-45",
  {
    variants: {
      variant: {
        primary: "bg-[var(--accent)] text-[var(--accent-ink)] hover:bg-[#ffd23d]",
        secondary:
          "border border-[var(--line-strong)] bg-[var(--surface-raised)] text-[var(--text)] hover:border-[var(--muted)]",
        danger: "bg-[var(--negative)] text-[#190707] hover:bg-[#ff7a7a]",
        ghost: "text-[var(--muted)] hover:bg-[var(--surface-raised)] hover:text-[var(--text)]",
      },
      size: {
        default: "h-9",
        sm: "h-8 px-2.5 text-xs",
        lg: "h-11 px-5",
        icon: "size-9 px-0",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size, className }))} {...props} />;
}

