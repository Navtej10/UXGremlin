import { useState, useEffect, type ReactNode } from 'react';

export type GremlinPose = 'idle' | 'investigating' | 'discovery' | 'completion' | 'confused';
export type GremlinSize = 'sm' | 'md' | 'lg' | 'hero';

interface GremlinProps {
  pose?: GremlinPose;
  size?: GremlinSize;
  className?: string;
  animate?: boolean;
  alt?: string;
}

const SIZE_CLASSES: Record<GremlinSize, string> = {
  sm: 'w-8 h-8',
  md: 'w-12 h-12',
  lg: 'w-20 h-20',
  hero: 'w-36 h-36',
};

export function Gremlin({
  pose = 'idle',
  size = 'md',
  className = '',
  animate = true,
  alt = 'UXGremlin Mascot',
}: GremlinProps) {
  const [currentPose, setCurrentPose] = useState<GremlinPose>(pose);
  const [isCrossfading, setIsCrossfading] = useState<boolean>(false);

  useEffect(() => {
    if (pose !== currentPose) {
      const raf = requestAnimationFrame(() => {
        setIsCrossfading(true);
      });
      const timer = setTimeout(() => {
        setCurrentPose(pose);
        setIsCrossfading(false);
      }, 150);
      return () => {
        cancelAnimationFrame(raf);
        clearTimeout(timer);
      };
    }
  }, [pose, currentPose]);

  const sizeClass = SIZE_CLASSES[size] || SIZE_CLASSES.md;
  const animationClass = animate ? 'animate-gremlin-idle' : '';

  return (
    <div
      className={`relative inline-flex items-center justify-center shrink-0 select-none ${sizeClass} ${animationClass} ${className}`}
      aria-label={alt}
      role="img"
    >
      <img
        src={`/mascot/${currentPose}.svg`}
        alt={alt}
        className={`w-full h-full object-contain transition-opacity duration-150 ease-in-out ${
          isCrossfading ? 'opacity-40' : 'opacity-100'
        }`}
      />
    </div>
  );
}

interface GremlinSpeechProps {
  children: ReactNode;
  className?: string;
  position?: 'right' | 'top' | 'bottom';
}

export function GremlinSpeech({
  children,
  className = '',
  position = 'right',
}: GremlinSpeechProps) {
  const tailPositionClass =
    position === 'right'
      ? 'before:absolute before:-left-1.5 before:top-4 before:w-3 before:h-3 before:bg-surface before:border-l before:border-b before:border-stone before:rotate-45'
      : position === 'top'
      ? 'before:absolute before:-bottom-1.5 before:left-6 before:w-3 before:h-3 before:bg-surface before:border-r before:border-b before:border-stone before:rotate-45'
      : 'before:absolute before:-top-1.5 before:left-6 before:w-3 before:h-3 before:bg-surface before:border-l before:border-t before:border-stone before:rotate-45';

  return (
    <div
      className={`relative bg-surface border border-stone rounded-2xl px-3.5 py-2 text-xs text-ink shadow-card leading-relaxed ${tailPositionClass} ${className}`}
    >
      {children}
    </div>
  );
}
