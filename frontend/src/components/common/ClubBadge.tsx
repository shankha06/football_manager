import { useState } from 'react';

interface ClubBadgeProps {
  clubId?: number | string;
  name: string;
  shortName?: string;
  primaryColor?: string;
  secondaryColor?: string;
  size?: number;
  className?: string;
}

function hashStr(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

function lighten(hex: string, pct: number): string {
  const c = hex.replace('#', '');
  if (c.length !== 6) return hex;
  const r = parseInt(c.substring(0, 2), 16);
  const g = parseInt(c.substring(2, 4), 16);
  const b = parseInt(c.substring(4, 6), 16);
  const nr = Math.min(255, Math.round(r + (255 - r) * pct));
  const ng = Math.min(255, Math.round(g + (255 - g) * pct));
  const nb = Math.min(255, Math.round(b + (255 - b) * pct));
  return `#${nr.toString(16).padStart(2, '0')}${ng.toString(16).padStart(2, '0')}${nb.toString(16).padStart(2, '0')}`;
}

function darken(hex: string, pct: number): string {
  const c = hex.replace('#', '');
  if (c.length !== 6) return hex;
  const r = parseInt(c.substring(0, 2), 16);
  const g = parseInt(c.substring(2, 4), 16);
  const b = parseInt(c.substring(4, 6), 16);
  const nr = Math.max(0, Math.round(r * (1 - pct)));
  const ng = Math.max(0, Math.round(g * (1 - pct)));
  const nb = Math.max(0, Math.round(b * (1 - pct)));
  return `#${nr.toString(16).padStart(2, '0')}${ng.toString(16).padStart(2, '0')}${nb.toString(16).padStart(2, '0')}`;
}

function getInitials(name: string, shortName?: string): string {
  if (shortName && shortName.length <= 3) return shortName.toUpperCase();
  const words = name.replace(/^(FC|CF|AC|AS|SS|SC|RC|CD|SD|CA|SE|CR|CS|US)\s+/i, '')
    .replace(/\s+(FC|CF|AC|SC|United|City|Town|Rovers|Wanderers|Albion|Athletic)$/i, '')
    .split(/\s+/);
  if (words.length === 1) return words[0].slice(0, 3).toUpperCase();
  return words.slice(0, 3).map(w => w[0]).join('').toUpperCase();
}

export default function ClubBadge({ clubId, name, shortName, primaryColor, secondaryColor, size = 40, className = '' }: ClubBadgeProps) {
  const [imgError, setImgError] = useState(false);
  const h = hashStr(name);
  const pc = primaryColor || '#3B82F6';
  const sc = secondaryColor || '#FFFFFF';
  const initials = getInitials(name, shortName);
  const shapeType = h % 4;
  const patternType = h % 6;
  const uid = `badge-${h}`;

  const fontSize = size < 24 ? 7 : size < 32 ? 8 : size < 48 ? 10 : 13;
  const textY = shapeType === 0 ? 55 : 52;

  const renderPattern = () => {
    switch (patternType) {
      case 1:
        return (
          <>
            <rect x="30" y="10" width="10" height="80" fill={sc} opacity="0.4" />
            <rect x="60" y="10" width="10" height="80" fill={sc} opacity="0.4" />
          </>
        );
      case 2:
        return <rect x="5" y="38" width="90" height="16" fill={sc} opacity="0.45" />;
      case 3:
        return <polygon points="0,0 100,0 100,45 0,55" fill={sc} opacity="0.25" />;
      case 4:
        return <polygon points="50,25 85,55 50,85 15,55" fill={sc} opacity="0.3" />;
      case 5:
        return <polygon points="0,15 25,0 100,75 75,100 0,25" fill={sc} opacity="0.3" />;
      default:
        return null;
    }
  };

  const renderShape = () => {
    switch (shapeType) {
      case 0: // Shield
        return (
          <svg viewBox="0 0 100 100" width={size} height={size} className={className}>
            <defs>
              <clipPath id={`${uid}-clip`}>
                <path d="M50,5 L90,15 L88,55 Q85,80 50,95 Q15,80 12,55 L10,15 Z" />
              </clipPath>
              <linearGradient id={`${uid}-grad`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={lighten(pc, 0.15)} />
                <stop offset="100%" stopColor={darken(pc, 0.2)} />
              </linearGradient>
            </defs>
            <g clipPath={`url(#${uid}-clip)`}>
              <rect x="0" y="0" width="100" height="100" fill={`url(#${uid}-grad)`} />
              {renderPattern()}
            </g>
            <path d="M50,5 L90,15 L88,55 Q85,80 50,95 Q15,80 12,55 L10,15 Z"
              fill="none" stroke={darken(pc, 0.4)} strokeWidth="2.5" />
            <text x="50" y={textY} textAnchor="middle" dominantBaseline="central"
              fill="#fff" fontSize={fontSize} fontWeight="800" fontFamily="system-ui, sans-serif"
              style={{ textShadow: '0 1px 2px rgba(0,0,0,0.5)' }}>
              {initials}
            </text>
          </svg>
        );
      case 1:
        return (
          <svg viewBox="0 0 100 100" width={size} height={size} className={className}>
            <defs>
              <clipPath id={`${uid}-clip`}>
                <circle cx="50" cy="50" r="44" />
              </clipPath>
              <linearGradient id={`${uid}-grad`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={lighten(pc, 0.15)} />
                <stop offset="100%" stopColor={darken(pc, 0.2)} />
              </linearGradient>
            </defs>
            <g clipPath={`url(#${uid}-clip)`}>
              <rect x="0" y="0" width="100" height="100" fill={`url(#${uid}-grad)`} />
              {renderPattern()}
            </g>
            <circle cx="50" cy="50" r="44" fill="none" stroke={darken(pc, 0.4)} strokeWidth="2.5" />
            <text x="50" y="52" textAnchor="middle" dominantBaseline="central"
              fill="#fff" fontSize={fontSize} fontWeight="800" fontFamily="system-ui, sans-serif"
              style={{ textShadow: '0 1px 2px rgba(0,0,0,0.5)' }}>
              {initials}
            </text>
          </svg>
        );
      case 2:
        return (
          <svg viewBox="0 0 100 100" width={size} height={size} className={className}>
            <defs>
              <clipPath id={`${uid}-clip`}>
                <rect x="8" y="8" width="84" height="84" rx="14" />
              </clipPath>
              <linearGradient id={`${uid}-grad`} x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor={lighten(pc, 0.1)} />
                <stop offset="100%" stopColor={darken(pc, 0.25)} />
              </linearGradient>
            </defs>
            <g clipPath={`url(#${uid}-clip)`}>
              <rect x="0" y="0" width="100" height="100" fill={`url(#${uid}-grad)`} />
              {renderPattern()}
            </g>
            <rect x="8" y="8" width="84" height="84" rx="14"
              fill="none" stroke={darken(pc, 0.4)} strokeWidth="2.5" />
            <text x="50" y="52" textAnchor="middle" dominantBaseline="central"
              fill="#fff" fontSize={fontSize} fontWeight="800" fontFamily="system-ui, sans-serif"
              style={{ textShadow: '0 1px 2px rgba(0,0,0,0.5)' }}>
              {initials}
            </text>
          </svg>
        );
      case 3:
        return (
          <svg viewBox="0 0 100 100" width={size} height={size} className={className}>
            <defs>
              <clipPath id={`${uid}-clip`}>
                <polygon points="50,6 90,28 90,72 50,94 10,72 10,28" />
              </clipPath>
              <linearGradient id={`${uid}-grad`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={lighten(pc, 0.12)} />
                <stop offset="100%" stopColor={darken(pc, 0.2)} />
              </linearGradient>
            </defs>
            <g clipPath={`url(#${uid}-clip)`}>
              <rect x="0" y="0" width="100" height="100" fill={`url(#${uid}-grad)`} />
              {renderPattern()}
            </g>
            <polygon points="50,6 90,28 90,72 50,94 10,72 10,28"
              fill="none" stroke={darken(pc, 0.4)} strokeWidth="2.5" />
            <text x="50" y="52" textAnchor="middle" dominantBaseline="central"
              fill="#fff" fontSize={fontSize} fontWeight="800" fontFamily="system-ui, sans-serif"
              style={{ textShadow: '0 1px 2px rgba(0,0,0,0.5)' }}>
              {initials}
            </text>
          </svg>
        );
      default:
        return null;
    }
  };

  if (clubId && !imgError) {
    return (
      <div className={`relative flex-shrink-0 flex items-center justify-center overflow-hidden rounded-full bg-white shadow-sm border border-gray-100 ${className}`} style={{ width: size, height: size }}>
        <img
          src={`/assets/clubs/${clubId}.svg`}
          alt={name}
          className="w-full h-full object-contain p-1"
          onError={(e) => {
            const target = e.target as HTMLImageElement;
            if (target.src.endsWith('.svg')) {
              target.src = target.src.replace('.svg', '.png');
            } else {
              setImgError(true);
            }
          }}
        />
      </div>
    );
  }

  return renderShape();
}
