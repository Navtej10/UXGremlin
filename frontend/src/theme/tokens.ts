// UXGremlin Design Tokens
// Visual Source of Truth - All colors, typography, shapes and shadows

export const TOKENS = {
  colors: {
    canvas: '#FAF9F6',
    surface: '#FFFFFF',
    gremlin: '#A8DF72',
    gremlinDark: '#6DBA3A',
    ink: '#263526',
    muted: '#6B776B',
    stone: '#EDE9DF',
    lilac: '#E9E4FF',
    lilacText: '#4B3FA0',
    severity: {
      critical: {
        bg: '#FCE5E3',
        fg: '#B3342B',
      },
      high: {
        bg: '#FCE5E3',
        fg: '#B3342B',
      },
      medium: {
        bg: '#FFF0D5',
        fg: '#8A5A00',
      },
      low: {
        bg: '#DFF3D8',
        fg: '#2F6B2A',
      },
      passed: {
        bg: '#DFF3D8',
        fg: '#2F6B2A',
      },
    },
  },
  shadows: {
    subtle: '0 1px 2px rgba(38, 53, 38, 0.04)',
    card: '0 1px 2px rgba(38, 53, 38, 0.04), 0 4px 16px rgba(38, 53, 38, 0.04)',
    popover: '0 8px 30px rgba(38, 53, 38, 0.08)',
  },
} as const;

export type SeverityLevel = 'critical' | 'high' | 'medium' | 'low' | 'passed';
