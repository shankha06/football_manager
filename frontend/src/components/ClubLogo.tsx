import React, { useState } from 'react';

interface ClubLogoProps {
    clubId: number | string;
    clubName: string;
    primaryColor?: string;
    secondaryColor?: string;
    size?: number;
}

export const ClubLogo: React.FC<ClubLogoProps> = ({
    clubId,
    clubName,
    primaryColor = '#FFFFFF',
    secondaryColor = '#000000',
    size = 40,
}) => {
    const [error, setError] = useState(false);

    // Get initials (up to 3 characters)
    const initials = clubName
        .split(' ')
        .map((word) => word[0])
        .join('')
        .substring(0, 3)
        .toUpperCase();

    const containerStyle: React.CSSProperties = {
        width: size,
        height: size,
        borderRadius: '50%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: primaryColor,
        color: secondaryColor,
        border: `2px solid ${secondaryColor}`,
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
        padding: '4px',
    };

    if (error) {
        return (
            <div style={containerStyle} title={clubName}>
                {initials}
            </div>
        );
    }

    // We check multiple extensions if needed, but for now we'll assume the script saves as .svg or .png
    // The API serves from /assets/clubs/
    return (
        <div style={containerStyle} title={clubName}>
            <img
                src={`http://localhost:8000/assets/clubs/${clubId}.svg`}
                onError={(e) => {
                    // Try .png if .svg fails
                    const target = e.target as HTMLImageElement;
                    if (target.src.endsWith('.svg')) {
                        target.src = target.src.replace('.svg', '.png');
                    } else {
                        setError(true);
                    }
                }}
                alt={clubName}
                style={imgStyle}
            />
        </div>
    );
};
