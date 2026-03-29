import * as React from "react";
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "ghost" | "outline" | "secondary";
  size?: "default" | "sm" | "lg";
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", ...props }, ref) => {
    return (
      <button
        className={cn(
          "inline-flex items-center justify-center font-medium transition-colors focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50",
          variant === "default" && "bg-primary text-white hover:bg-primary-hover",
          variant === "ghost" && "hover:bg-gray-100 text-gray-700",
          variant === "outline" && "border border-gray-300 bg-transparent hover:bg-gray-50",
          variant === "secondary" && "bg-white text-gray-900 hover:bg-gray-100",
          size === "default" && "h-10 px-4 py-2",
          size === "sm" && "h-9 px-3 text-xs",
          size === "lg" && "h-12 px-8 text-lg",
          className
        )}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button };
