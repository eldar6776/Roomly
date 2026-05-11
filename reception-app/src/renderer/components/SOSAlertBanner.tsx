import React from 'react';
import { Room } from '@shared/types';
import { Button } from './ui/button';

interface SOSAlertBannerProps {
  rooms: Room[];
  onRoomClick: (room: Room) => void;
}

const SOSAlertBanner: React.FC<SOSAlertBannerProps> = ({ rooms, onRoomClick }) => {
  const sosRooms = rooms.filter((r) => r.sos_active);

  if (sosRooms.length === 0) {
    return null;
  }

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-red-600 text-white shadow-2xl animate-pulse">
      <div className="container mx-auto px-4 py-3">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <span className="text-3xl animate-bounce">🆘</span>
            <div className="flex flex-col">
              <span className="text-lg font-bold">SOS ALARM AKTIVAN</span>
              <span className="text-sm opacity-90">
                {sosRooms.length} {sosRooms.length === 1 ? 'soba zahtijeva' : 'sobe zahtijevaju'} hitnu pomoć
              </span>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            {sosRooms.map((room) => (
              <Button
                key={room.room_number}
                onClick={() => onRoomClick(room)}
                variant="outline"
                className="bg-white text-red-600 hover:bg-red-50 font-bold border-2 border-white"
              >
                🆘 Soba {room.room_number}
                {room.sos_timestamp && (
                  <span className="ml-2 text-xs opacity-75">
                    {new Date(room.sos_timestamp).toLocaleTimeString('hr-HR', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </span>
                )}
              </Button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default SOSAlertBanner;
