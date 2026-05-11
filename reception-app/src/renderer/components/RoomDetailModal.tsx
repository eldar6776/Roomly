import React, { useState } from 'react';
import { Room } from '@shared/types';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from './ui/dialog';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { DatePicker } from './ui/date-picker';
import { TimePicker } from './ui/time-picker';
import { useToast } from './ui/toast';

interface RoomDetailModalProps {
  room: Room | null;
  isOpen: boolean;
  onClose: () => void;
  onCheckIn: (checkOutDate: string, checkOutTime: string) => void;
  onCheckOut: () => void;
  onExtendStay: (newCheckOutDate: string, newCheckOutTime: string) => void;
  onProgramCard: (checkOutDate: string, checkOutTime: string) => void;
  cardReaderAvailable: boolean;
}

const RoomDetailModal: React.FC<RoomDetailModalProps> = ({
  room,
  isOpen,
  onClose,
  onCheckIn,
  onCheckOut,
  onExtendStay,
  onProgramCard,
  cardReaderAvailable,
}) => {
  const [guestInTemp, setGuestInTemp] = useState(22);
  const [guestOutTemp, setGuestOutTemp] = useState(18);
  const [currentSetpoint, setCurrentSetpoint] = useState(22);
  const [language, setLanguage] = useState('0'); // 0=SRB, 1=ENG, 2=GER
  const { toast } = useToast();
  
  // Novi state za datum i vrijeme
  const getTodayDate = () => {
    const today = new Date();
    return today.toISOString().split('T')[0];
  };
  
  const getTomorrowDate = () => {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    return tomorrow.toISOString().split('T')[0];
  };
  
  const [checkOutDate, setCheckOutDate] = useState(getTomorrowDate());
  const [checkOutTime, setCheckOutTime] = useState('13:00');
  
  // Ažuriraj state kada se room promeni
  React.useEffect(() => {
    if (room) {
      setGuestInTemp(room.guest_in_temp || 22);
      setGuestOutTemp(room.guest_out_temp || 18);
      setCurrentSetpoint(room.setpoint_temp || 22);
      
      // Ako soba nema gosta, postavi sutra kao checkout
      if (!room.guest_pin) {
        setCheckOutDate(getTomorrowDate());
        setCheckOutTime('13:00');
      } else {
        // Ako soba ima gosta i postoji pin_expiry, učitaj taj datum za produžavanje
        if (room.pin_expiry) {
          try {
            // Format: "DD.MM.YYYY HH:MM" ili "YYYY-MM-DD HH:MM"
            const expiryParts = room.pin_expiry.split(' ');
            if (expiryParts.length >= 2) {
              const datePart = expiryParts[0];
              const timePart = expiryParts[1];
              
              // Konvertuj DD.MM.YYYY u YYYY-MM-DD za date picker
              if (datePart.includes('.')) {
                const [day, month, year] = datePart.split('.');
                setCheckOutDate(`${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`);
              } else {
                setCheckOutDate(datePart); // Već u YYYY-MM-DD formatu
              }
              
              setCheckOutTime(timePart.substring(0, 5)); // HH:MM
            }
          } catch (error) {
            console.error('Failed to parse pin_expiry:', error);
            // Fallback na sutra
            setCheckOutDate(getTomorrowDate());
            setCheckOutTime('13:00');
          }
        } else {
          // Ako nema pin_expiry, postavi sutra
          setCheckOutDate(getTomorrowDate());
          setCheckOutTime('13:00');
        }
      }
    }
  }, [room]);

  if (!room) return null;

  const handleSetGuestTemps = async () => {
    try {
      await window.electronAPI.rooms.setGuestTemps(room.room_number, {
        guest_in_temp: guestInTemp,
        guest_out_temp: guestOutTemp,
      });
      toast.success('Guest temperature ažurirane');
    } catch (error) {
      console.error('Failed to set guest temps:', error);
      toast.error('Nije moguće postaviti guest temperature');
    }
  };
  
  const handleSetCurrentSetpoint = async () => {
    try {
      await window.electronAPI.rooms.setTemperature(room.room_number, currentSetpoint);
      toast.success(`Temperatura postavljena na ${currentSetpoint}°C`);
    } catch (error) {
      console.error('Failed to set temperature:', error);
      toast.error('Nije moguće postaviti temperaturu');
    }
  };

  const handleThermostatControl = async (action: 'on' | 'off' | 'heating' | 'cooling') => {
    try {
      await window.electronAPI.rooms.controlThermostat(room.room_number, action);
      toast.success(`Termostat postavljen na ${action.toUpperCase()}`);
    } catch (error) {
      console.error('Failed to control thermostat:', error);
      toast.error('Nije moguće kontrolisati termostat');
    }
  };

  const handleSetLanguage = async () => {
    try {
      await window.electronAPI.rooms.setLanguage(room.room_number, language);
      const langNames = {'0': 'Srpski', '1': 'English', '2': 'Deutsch'};
      toast.success(`Jezik displeja postavljen na ${langNames[language as keyof typeof langNames]}`);
    } catch (error) {
      console.error('Failed to set language:', error);
      toast.error('Nije moguće postaviti jezik');
    }
  };

  const handleCheckIn = () => {
    onCheckIn(checkOutDate, checkOutTime);
  };

  const handleExtendStay = () => {
    onExtendStay(checkOutDate, checkOutTime);
  };

  const handleProgramCard = () => {
    onProgramCard(checkOutDate, checkOutTime);
  };

  const getStatusColor = () => {
    if (!room.online) return 'text-yellow-500';
    if (room.guest_pin) return 'text-blue-500';
    if (room.occupied) return 'text-red-500';
    return 'text-green-500';
  };

  const getStatusText = () => {
    if (!room.online) return 'Offline';
    if (room.guest_pin) return 'Checked In';
    if (room.occupied) return 'Occupied';
    return 'Available';
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-2xl">Room {room.room_number}</DialogTitle>
          <DialogDescription>
            <span className={`font-semibold ${getStatusColor()}`}>
              {getStatusText()}
            </span>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Current Status */}
          <div className="grid grid-cols-2 gap-4 p-4 bg-background/50 rounded-lg">
            <div>
              <Label className="text-muted-foreground">Kartica u odlagaču</Label>
              <div className="font-semibold">{room.card_inserted ? '✓ Ubačena' : '✗ Prazno'}</div>
            </div>
            <div>
              <Label className="text-muted-foreground">Online</Label>
              <div className="font-semibold">{room.online ? '✓ Yes' : '✗ No'}</div>
            </div>
            <div>
              <Label className="text-muted-foreground">Current Temperature</Label>
              <div className="font-semibold text-xl">{room.current_temp !== null ? `${room.current_temp}°C` : '--'}</div>
            </div>
            <div>
              <Label className="text-muted-foreground">Target Temperature</Label>
              <div className="font-semibold text-xl">{room.setpoint_temp !== null ? `${room.setpoint_temp}°C` : '--'}</div>
            </div>
          </div>

          {/* Guest Info */}
          {room.guest_pin && (
            <div className="p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
              <Label className="text-blue-400 font-semibold">Guest Information</Label>
              <div className="mt-2 space-y-1">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">PIN:</span>
                  <span className="font-mono font-bold text-lg">{room.guest_pin}</span>
                </div>
                {room.pin_expiry && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Važi do:</span>
                    <span className="font-mono text-sm text-blue-300">{room.pin_expiry}</span>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Check-In/Out Date & Time Section */}
          {room.online && (
            <div className="p-4 bg-primary/5 border border-primary/20 rounded-lg space-y-4">
              <Label className="text-lg font-semibold">
                {room.guest_pin ? '📅 Produženje Boravka' : '📅 Check-In Rezervacija'}
              </Label>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <DatePicker
                  label="Datum Odlaska (Check-Out)"
                  value={checkOutDate}
                  onChange={setCheckOutDate}
                  min={getTodayDate()}
                />
                
                <TimePicker
                  label="Vrijeme Odlaska"
                  value={checkOutTime}
                  onChange={setCheckOutTime}
                />
              </div>
              
              <div className="text-sm text-muted-foreground">
                ℹ️ PIN će važiti do: {checkOutDate} u {checkOutTime}h
              </div>

              {/* Action Buttons - unutar kontejnera */}
              <div className="space-y-2 pt-2">
                <div className="flex gap-2">
                  {!room.guest_pin ? (
                    <Button onClick={handleCheckIn} className="flex-1" size="lg">
                      ✅ Check In Guest
                    </Button>
                  ) : (
                    <Button onClick={handleExtendStay} variant="default" className="flex-1" size="lg">
                      ⏱️ Produži Boravak
                    </Button>
                  )}
                  <Button onClick={onClose} variant="outline" className="flex-1" size="lg">
                    Close
                  </Button>
                </div>

                {cardReaderAvailable && (
                  <Button onClick={handleProgramCard} variant="outline" className="w-full font-semibold border-2 text-orange-400 hover:text-orange-300" size="lg">
                    {room.guest_pin ? '💳 Produži karticu' : '💳 Upiši karticu (Check-In)'}
                  </Button>
                )}
              </div>
            </div>
          )}

          {/* Current Setpoint Control */}
          {room.online && (
            <div className="space-y-4">
              <Label className="text-lg font-semibold">Room Temperature Control</Label>
              
              <div className="space-y-3">
                <div>
                  <Label htmlFor="currentSetpoint">Current Setpoint: {currentSetpoint}°C</Label>
                  <input
                    id="currentSetpoint"
                    type="range"
                    min="18"
                    max="30"
                    value={currentSetpoint}
                    onChange={(e) => setCurrentSetpoint(Number(e.target.value))}
                    className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer"
                  />
                </div>

                <Button onClick={handleSetCurrentSetpoint} className="w-full">
                  Set Room Temperature
                </Button>
              </div>
            </div>
          )}
          
          {/* Thermostat Controls */}
          {room.online && (
            <div className="space-y-4">
              <Label className="text-lg font-semibold">Thermostat Control</Label>
              
              <div className="grid grid-cols-2 gap-2">
                <Button
                  variant="outline"
                  onClick={() => handleThermostatControl('heating')}
                >
                  🔥 Heating
                </Button>
                <Button
                  variant="outline"
                  onClick={() => handleThermostatControl('cooling')}
                >
                  ❄️ Cooling
                </Button>
                <Button
                  variant="outline"
                  onClick={() => handleThermostatControl('on')}
                >
                  ✅ On
                </Button>
                <Button
                  variant="outline"
                  onClick={() => handleThermostatControl('off')}
                >
                  ⭕ Off
                </Button>
              </div>
            </div>
          )}

          {/* Room Display Language */}
          {room.online && (
            <div className="space-y-4">
              <Label className="text-lg font-semibold">Room Display Language</Label>
              
              <div className="space-y-3">
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="w-full p-2 bg-background border border-border rounded-lg"
                >
                  <option value="0">🇷🇸 Srpski</option>
                  <option value="1">🇬🇧 English</option>
                  <option value="2">🇩🇪 Deutsch</option>
                </select>

                <Button onClick={handleSetLanguage} className="w-full">
                  Set Display Language
                </Button>
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex gap-2 pt-4 border-t border-border">
            {room.guest_pin && (
              <Button onClick={onCheckOut} variant="destructive" className="flex-1" size="lg">
                🚪 Check Out
              </Button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default RoomDetailModal;
