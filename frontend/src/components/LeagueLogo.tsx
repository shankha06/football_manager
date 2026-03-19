import React, { useState } from 'react';

interface LeagueLogoProps {
    leagueId: number | string;
    leagueName: string;
    size?: number;
}

export const LeagueLogo: React.FC<LeagueLogoProps> = ({
    leagueId,
    leagueName,
    size = 40,
}) => {
    const [error, setError] = useState(false);

    // Get initials (up to 3 characters)
    const initials = leagueName
        .split(' ')
        .map((word) => word[0])
        .join('')
        .substring(0, 3)
        .toUpperCase();

    const containerStyle: React.CSSProperties = {
        width: size,
        height: size,
        borderRadius: '4px', // Leagues often have non-circular logos
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: '#333333',
        color: '#FFFFFF',
        fontWeight: 'bold',
        fontSize: size * 0.4,
        overflow: 'hidden',
        flexShrink: 0,
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
    };

    const imgStyle: React.CSSProperties = {
        width: '100%',
        height: '100%',
        objectFit: 'contain',
        padding: '2px',
    };

    if (error) {
        return (
            <div style={containerStyle} title={leagueName}>
                {initials}
            </div>
        );
    }

    return (
        <div style={containerStyle} title={leagueName}>
            <img
                src={`/assets/leagues/${leagueId}.svg`}
                onError={(e) => {
                    const target = e.target as HTMLImageElement;
                    if (target.src.endsWith('.svg')) {
                        target.src = target.src.replace('.svg', '.png');
                    } else {
                        setError(true);
                    }
                }}
                alt={leagueName}
                style={imgStyle}
            />
        </div>
    );
};
