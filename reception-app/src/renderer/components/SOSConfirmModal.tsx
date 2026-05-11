import React, { useState } from 'react';
import { Room } from '@shared/types';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Button } from './ui/button';
import { useToast } from './ui/toast';

interface SOSConfirmModalProps {
  room: Room | null;
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (room: Room) => void;
}

const SOSConfirmModal: React.FC<SOSConfirmModalProps> = ({
  room,
  isOpen,
  onClose,
  onConfirm,
}) => {
  const [isResetting, setIsResetting] = useState(false);
  const { toast } = useToast();

  if (!room) return null;

  const handleConfirm = async () => {
    setIsResetting(true);
    try {
      await onConfirm(room);
      onClose();
    } catch (error) {
      console.error('Failed to reset SOS:', error);
      toast.error('Greška prilikom resetovanja SOS alarma: ' + (error as Error).message);
    } finally {
      setIsResetting(false);
    }
  };

  const sosTime = room.sos_timestamp
    ? new Date(room.sos_timestamp).toLocaleString('hr-HR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    : 'Nepoznato';

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md border-4 border-red-500">
        <DialogHeader>
          <DialogTitle className="text-2xl font-bold text-red-600 flex items-center gap-2">
            <span className="text-4xl">🆘</span>
            <span>SOS ALARM - Soba <span className="text-3xl font-black">{room.room_number}</span></span>
          </DialogTitle>
          <DialogDescription className="text-base font-semibold text-gray-800">
            Potvrdi da je osoblje reagovalo na hitni poziv
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="bg-red-50 border-2 border-red-200 rounded-lg p-4">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="font-semibold text-gray-700">Soba:</div>
                <div className="text-2xl font-black text-gray-900">{room.room_number}</div>
              </div>
              <div>
                <div className="font-semibold text-gray-700">Vrijeme alarma:</div>
                <div className="text-base font-bold text-gray-900">{sosTime}</div>
              </div>
              <div>
                <div className="font-semibold text-gray-700">Status:</div>
                <div className="text-red-600 font-bold">
                  {room.card_inserted ? '🔴 Gost u sobi' : '🔵 Zauzeta'}
                </div>
              </div>
              <div>
                <div className="font-semibold text-gray-700">Temperatura:</div>
                <div className="text-base font-bold text-gray-900">{room.current_temp ? `${room.current_temp}°C` : '--'}</div>
              </div>
            </div>
          </div>

          <div className="bg-yellow-100 border-2 border-yellow-500 rounded-lg p-4">
            <p className="text-base text-center font-bold text-gray-900">
              <span className="text-yellow-700 text-lg">⚠️ UPOZORENJE:</span><br/>
              Klikni <span className="text-red-600">"Potvrdi"</span> samo nakon što je osoblje reagovalo i riješilo situaciju.
            </p>
          </div>
        </div>

        <div className="flex justify-end gap-3">
          <Button
            onClick={onClose}
            variant="outline"
            disabled={isResetting}
            className="min-w-[100px]"
          >
            Otkaži
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={isResetting}
            className="min-w-[100px] bg-red-600 hover:bg-red-700"
          >
            {isResetting ? 'Resetujem...' : '✅ Potvrdi'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default SOSConfirmModal;
