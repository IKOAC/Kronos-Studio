import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "group/button relative inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-none font-semibold uppercase tracking-[0.1em] whitespace-nowrap transition-colors duration-150 outline-none select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#FF3D00] active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "border-b-2 border-[#FF3D00] bg-transparent text-[#FF3D00] hover:border-foreground hover:text-foreground",
        outline: "border border-foreground/70 bg-transparent text-foreground hover:bg-foreground hover:text-background",
        secondary: "border border-border bg-muted text-foreground hover:border-foreground",
        ghost: "border-b border-transparent bg-transparent text-muted-foreground hover:border-foreground hover:text-foreground",
        destructive: "border border-destructive/70 bg-destructive/10 text-destructive hover:bg-destructive/20",
        link: "border-b-2 border-[#FF3D00] text-[#FF3D00] hover:text-foreground"
      },
      size: {
        default: "min-h-11 px-3 py-2 text-[11px]",
        xs: "min-h-9 px-2 py-1 text-[10px]",
        sm: "min-h-10 px-3 py-2 text-[10px]",
        lg: "min-h-12 px-5 py-3 text-xs",
        icon: "size-11 p-0",
        "icon-xs": "size-9 p-0",
        "icon-sm": "size-10 p-0",
        "icon-lg": "size-12 p-0"
      }
    },
    defaultVariants: {
      variant: "default",
      size: "default"
    }
  }
);

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
