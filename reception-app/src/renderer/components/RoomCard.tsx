import React from 'react';
import { Room } from '@shared/types';

interface RoomCardProps {
  room: Room;
  printerAvailable?: boolean;
  onClick: () => void;
}

const RoomCard: React.FC<RoomCardProps> = ({ room, printerAvailable = false, onClick }) => {
  // Status colors and labels prema toplik sys.txt dokumentaciji:
  // - Offline = nema komunikacije sa ESP
  // - Zauzeta = validan pin u EEPROM-u (aktivan check-in)
  // - Gost u sobi = kartica u odlagaču
  // - Slobodna = online, nema pina, nema kartice
  const getStatusInfo = () => {
    if (!room.online) {
      return {
        color: 'bg-gray-500/20 border-gray-500',
        label: '🔴 Offline',
        textColor: 'text-gray-400',
        icon: '⚠️'
      };
    }

    // Gost u sobi (kartica u odlagaču) - crvena
    if (room.card_inserted) {
      return {
        color: 'bg-red-500/20 border-red-500',
        label: '🔴 Gost u sobi',
        textColor: 'text-red-400',
        icon: '👤'
      };
    }

    // Zauzeta (check-in aktivan, ali nema kartice) - plava
    if (room.active_pin) {
      return {
        color: 'bg-blue-500/20 border-blue-500',
        label: '🔵 Zauzeta (Check-in)',
        textColor: 'text-blue-400',
        icon: '🔑'
      };
    }

    // Online i slobodna - zelena
    return {
      color: 'bg-green-500/20 border-green-500',
      label: '🟢 Slobodna',
      textColor: 'text-green-400',
      icon: '✓'
    };
  };

  const status = getStatusInfo();

  return (
    <div
      onClick={onClick}
      className={`relative p-6 rounded-lg border-2 cursor-pointer transition-all hover:scale-105 hover:shadow-xl ${status.color} ${
        room.sos_active ? 'ring-4 ring-red-500 animate-pulse' : ''
      }`}
    >
      {/* SOS Badge - Highest Priority */}
      {room.sos_active && (
        <div className="absolute -top-2 -right-2 z-10">
          <div className="bg-red-600 text-white px-3 py-1 rounded-full text-xs font-bold animate-bounce shadow-lg border-2 border-white">
            🆘 SOS
          </div>
        </div>
      )}

      {/* Room Number */}
      <div className="text-3xl font-bold mb-2">Room {room.room_number}</div>

      {/* Status Badge */}
      <div className={`inline-block px-3 py-1 rounded-full text-xs font-semibold mb-4 ${status.textColor} bg-background/50`}>
        {status.label}
      </div>

      {/* Temperature Display */}
      {room.online && (
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Current:</span>
            <span className="font-semibold">{room.current_temp !== null ? `${room.current_temp}` : '--'}°C</span>
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Target:</span>
            <span className="font-semibold">{room.setpoint_temp || '--'}°C</span>
          </div>
        </div>
      )}

      {/* Guest Info + Reprint */}
      {room.active_pin && (
        <div className="mt-4 pt-4 border-t border-border flex items-center justify-between">
          <div className="text-xs text-muted-foreground">PIN: {room.active_pin}</div>
          {printerAvailable && (
            <button
              title="Re-štampaj slip"
              className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded"
              onClick={(e) => {
                e.stopPropagation();
                window.electronAPI.printer.reprint({
                  roomNumber: room.room_number,
                  pin: room.active_pin!,
                  checkoutDate: (room as any).expiry ?? '',
                  language: (room as any).language ?? 'srb',
                }).catch((err: Error) => console.error('Reprint failed:', err));
              }}
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M17 17H7a2 2 0 01-2-2V9a2 2 0 012-2h10a2 2 0 012 2v6a2 2 0 01-2 2zm-5 2v2m0-10V5" />
              </svg>
            </button>
          )}
        </div>
      )}

      {/* Offline Indicator */}
      {!room.online && (
        <div className="absolute top-2 right-2">
          <svg className="h-5 w-5 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
      )}
    </div>
  );
};

export default RoomCard;
