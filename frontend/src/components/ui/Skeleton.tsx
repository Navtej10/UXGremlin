import type { HTMLAttributes } from 'react';

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {
  rounded?: 'sm' | 'md' | 'lg' | 'full';
}

const ROUNDED_CLASSES = {
  sm: 'rounded',
  md: 'rounded-xl',
  lg: 'rounded-2xl',
  full: 'rounded-full',
};

export function Skeleton({
  rounded = 'md',
  className = '',
  ...props
}: SkeletonProps) {
  return (
    <div
      className={`animate-pulse bg-stone/60 ${ROUNDED_CLASSES[rounded]} ${className}`}
      {...props}
    />
  );
}
