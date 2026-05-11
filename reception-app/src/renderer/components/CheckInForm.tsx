import React, { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { useToast } from './ui/toast';

interface CheckInFormProps {
  isOpen: boolean;
  onClose: () => void;
  roomNumber: string;
  onSuccess: () => void;
  printerAvailable?: boolean;
}

const CheckInForm: React.FC<CheckInFormProps> = ({
  isOpen,
  onClose,
  roomNumber,
  onSuccess,
  printerAvailable = false,
}) => {
  const [checkoutDate, setCheckoutDate] = useState('');
  const [checkoutTime, setCheckoutTime] = useState('12:00');
  const [language, setLanguage] = useState('srb');
  const [guestPin, setGuestPin] = useState('');
  const [useAutoPin, setUseAutoPin] = useState(true);
  const [loading, setLoading] = useState(false);
  const [dayTemp, setDayTemp] = useState(22);
  const [nightTemp, setNightTemp] = useState(20);
  const [shouldPrint, setShouldPrint] = useState(true);
  const { toast } = useToast();

  // Load default settings
  useEffect(() => {
    const loadDefaults = async () => {
      try {
        const checkoutTimeSetting = await window.electronAPI.settings.get('checkout_time');
        const dayTempSetting = await window.electronAPI.settings.get('default_temp_day');
        const nightTempSetting = await window.electronAPI.settings.get('default_temp_night');
        const langSetting = await window.electronAPI.settings.get('default_language');

        if (checkoutTimeSetting) setCheckoutTime(checkoutTimeSetting);
        if (dayTempSetting) setDayTemp(Number(dayTempSetting));
        if (nightTempSetting) setNightTemp(Number(nightTempSetting));
        if (langSetting) setLanguage(langSetting);

        // Set default checkout date to tomorrow
        const tomorrow = new Date();
        tomorrow.setDate(tomorrow.getDate() + 1);
        setCheckoutDate(tomorrow.toISOString().split('T')[0]);
      } catch (error) {
        console.error('Failed to load defaults:', error);
      }
    };

    if (isOpen) {
      loadDefaults();
      if (useAutoPin) {
        generatePin();
      }
    }
  }, [isOpen]);

  const generatePin = async () => {
    try {
      const pin = await window.electronAPI.utils.generatePin();
      setGuestPin(pin);
    } catch (error) {
      console.error('Failed to generate PIN:', error);
      toast.error('Nije moguće generisati PIN. Provjerite konekciju sa RPI serverom.');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      // Validate PIN
      if (!useAutoPin && guestPin.length !== 4) {
        toast.warning('PIN mora biti 4 cifre');
        setLoading(false);
        return;
      }

      // Check PIN collision (pita RPI da li je PIN već u upotrebi)
      try {
        const collision = await window.electronAPI.utils.checkPinCollision(guestPin);
        if (collision) {
          toast.warning('Ovaj PIN je već u upotrebi u nekoj drugoj sobi. Kliknite "🔄" da generirate novi.');
          setLoading(false);
          return;
        }
      } catch (error) {
        console.error('Failed to check PIN collision:', error);
        toast.error('Nije moguće provjeriti PIN. Provjerite konekciju sa RPI serverom.');
        setLoading(false);
        return;
      }

      // Format expiry date and time for backend
      const [year, month, day] = checkoutDate.split('-');
      const expiryDateFormatted = `${day}.${month}.${year}`; // DD.MM.YYYY
      const expiryTime = checkoutTime; // HH:MM

      // Send PIN to room with expiry
      await window.electronAPI.rooms.setPin(roomNumber, {
        pin: guestPin,
        expiry_date: expiryDateFormatted,
        expiry_time: expiryTime,
        language,
        day_temp: dayTemp,
        night_temp: nightTemp,
      });

      // Save guest to LOCAL database (WITHOUT PIN - PIN only in UL/RPI!)
      await window.electronAPI.database.guests.create({
        room_number: roomNumber,
        check_out_date: `${checkoutDate}T${checkoutTime}:00`,
        language,
      });

      // Create system log entry (app action)
      await window.electronAPI.database.systemLogs.create({
        room_number: roomNumber,
        event_type: 'CHECK_IN',
        description: `Guest checked in to Room ${roomNumber}, checkout: ${checkoutDate} ${checkoutTime}`,
        user_role: 'RECEPTION',
      });

      // Print slip
      if (printerAvailable && shouldPrint) {
        try {
          const checkoutDateTime = `${checkoutDate} ${checkoutTime}`;
          await window.electronAPI.printer.print({
            roomNumber,
            pin: guestPin,
            checkoutDate: checkoutDateTime,
            language,
          });
        } catch (printError) {
          console.error('Print failed:', printError);
          // Ne prekida check-in ako print ne uspije
        }
      }

      toast.success(`Gost je uspješno prijavljen u sobu ${roomNumber}`);
      onSuccess();
      onClose();
    } catch (error) {
      console.error('Check-in failed:', error);
      toast.error('Check-in neuspješan: ' + (error as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const getLanguageFlag = (lang: string) => {
    switch (lang) {
      case 'srb': return '🇷🇸';
      case 'eng': return '🇬🇧';
      case 'ger': return '🇩🇪';
      default: return '';
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-2xl">Check In - Room {roomNumber}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Checkout Date */}
          <div>
            <Label htmlFor="checkoutDate">Checkout Date *</Label>
            <Input
              id="checkoutDate"
              type="date"
              value={checkoutDate}
              onChange={(e) => setCheckoutDate(e.target.value)}
              required
              min={new Date().toISOString().split('T')[0]}
            />
          </div>

          {/* Checkout Time */}
          <div>
            <Label htmlFor="checkoutTime">Checkout Time *</Label>
            <Input
              id="checkoutTime"
              type="time"
              value={checkoutTime}
              onChange={(e) => setCheckoutTime(e.target.value)}
              required
            />
          </div>

          {/* Language Selection */}
          <div>
            <Label>Language / Jezik / Sprache *</Label>
            <Select value={language} onValueChange={setLanguage}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="srb">{getLanguageFlag('srb')} Srpski</SelectItem>
                <SelectItem value="eng">{getLanguageFlag('eng')} English</SelectItem>
                <SelectItem value="ger">{getLanguageFlag('ger')} Deutsch</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* PIN Input */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <Label>Guest PIN</Label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={useAutoPin}
                  onChange={(e) => {
                    setUseAutoPin(e.target.checked);
                    if (e.target.checked) generatePin();
                  }}
                />
                Auto-generate
              </label>
            </div>

            {useAutoPin ? (
              <div className="flex gap-2">
                <Input
                  value={guestPin}
                  readOnly
                  className="text-2xl font-mono text-center"
                />
                <Button type="button" onClick={generatePin} variant="outline">
                  🔄
                </Button>
              </div>
            ) : (
              <Input
                type="text"
                pattern="[0-9]{4}"
                maxLength={4}
                value={guestPin}
                onChange={(e) => setGuestPin(e.target.value.replace(/\D/g, ''))}
                placeholder="Enter 4-digit PIN"
                required
                className="text-2xl font-mono text-center"
              />
            )}
          </div>

          {/* Submit Buttons */}
          <div className="flex gap-2 pt-4">
            <Button type="submit" disabled={loading} className="flex-1" size="lg">
              {loading ? 'Checking In...' : 'Check In'}
            </Button>
            <Button type="button" onClick={onClose} variant="outline" className="flex-1" size="lg">
              Cancel
            </Button>
          </div>

          {/* Printer checkbox - vidljiv samo ako je printer dostupan */}
          {printerAvailable && (
            <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer select-none">
              <input
                type="checkbox"
                checked={shouldPrint}
                onChange={(e) => setShouldPrint(e.target.checked)}
                className="w-4 h-4"
              />
              🖨️ Štampaj PIN slip
            </label>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default CheckInForm;
