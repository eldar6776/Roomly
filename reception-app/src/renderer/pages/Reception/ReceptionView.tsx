import React, { useState, useEffect, useRef } from 'react';
import { Room } from '@shared/types';
import RoomCard from '../../components/RoomCard';
import RoomDetailModal from '../../components/RoomDetailModal';
import CheckInForm from '../../components/CheckInForm';
import SOSAlertBanner from '../../components/SOSAlertBanner';
import SOSConfirmModal from '../../components/SOSConfirmModal';
import { Button } from '../../components/ui/button';
import { useToast } from '../../components/ui/toast';
import { useConfirm } from '../../components/ui/confirm-dialog';

interface ReceptionViewProps {
  onLogout: () => void;
}

export default function ReceptionView({ onLogout }: ReceptionViewProps) {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [selectedRoom, setSelectedRoom] = useState<Room | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showCheckInForm, setShowCheckInForm] = useState(false);
  const [showSOSModal, setShowSOSModal] = useState(false);
  const [sosRoom, setSOSRoom] = useState<Room | null>(null);
  const [cardReaderAvailable, setCardReaderAvailable] = useState(false);
  const [printerAvailable, setPrinterAvailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [initialized, setInitialized] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [previousSOSRooms, setPreviousSOSRooms] = useState<Set<string>>(new Set());
  const { toast } = useToast();
  const confirm = useConfirm();
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch rooms from API
  const fetchRooms = async () => {
    try {
      const data = await window.electronAPI.rooms.getAll();
      setRooms(data);
      setLastUpdate(new Date());
      setInitialized(true);
    } catch (error) {
      console.error('Failed to fetch rooms:', error);
    } finally {
      setLoading(false);
    }
  };

  const startAutoRefresh = () => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => {
      fetchRooms();
    }, 10000);
  };

  // Pravi Refresh: trigerira mDNS rediscovery za offline sobe, čeka resoluciju, pa fetcha
  const handleRefresh = async () => {
    if (isDiscovering) return;
    setIsDiscovering(true);
    try {
      const offlineCount = rooms.filter(r => !r.online).length;
      if (offlineCount > 0) {
        await window.electronAPI.rooms.rediscover();
        // Daj mDNS resolve threadovima vremena da završe (~3.5s je dovoljno)
        await new Promise(resolve => setTimeout(resolve, 3500));
      }
      await fetchRooms();
      startAutoRefresh(); // Reset interval da ne okida odmah nakon manual refresha
    } catch (error) {
      console.error('Failed to refresh:', error);
      await fetchRooms();
    } finally {
      setIsDiscovering(false);
    }
  };

  // Initial load
  useEffect(() => {
    fetchRooms();
    // Provjeri printer jednom pri startu (silent, ne blokira UI)
    window.electronAPI.printer.checkStatus()
      .then((res: { available: boolean }) => setPrinterAvailable(Boolean(res?.available)))
      .catch(() => setPrinterAvailable(false));
  }, []);

  // Auto-refresh every 10 seconds
  useEffect(() => {
    startAutoRefresh();
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, []);

  // Update selectedRoom when rooms refresh
  useEffect(() => {
    if (selectedRoom && rooms.length > 0) {
      const updatedRoom = rooms.find(r => r.room_number === selectedRoom.room_number);
      if (updatedRoom) {
        setSelectedRoom(updatedRoom);
      }
    }
  }, [rooms]);

  // Monitor SOS status changes and log new activations
  useEffect(() => {
    if (rooms.length === 0) return;

    const currentSOSRooms = new Set(
      rooms.filter(r => r.sos_active).map(r => r.room_number)
    );

    // Detect newly activated SOS alarms
    currentSOSRooms.forEach(roomNumber => {
      if (!previousSOSRooms.has(roomNumber)) {
        // New SOS alarm detected - create log entry
        const room = rooms.find(r => r.room_number === roomNumber);
        if (room) {
          window.electronAPI.database.systemLogs.create({
            room_number: room.room_number,
            event_type: 'SOS_ACTIVATED',
            description: `🆘 SOS alarm aktiviran u sobi ${room.room_number}`,
            user_role: 'SYSTEM',
          }).catch(err => {
            console.error('Failed to log SOS activation:', err);
          });
        }
      }
    });

    // Update tracking set
    setPreviousSOSRooms(currentSOSRooms);
  }, [rooms]);

  const handleRoomClick = async (room: Room) => {
    setSelectedRoom(room);
    setShowDetailModal(true);
    setCardReaderAvailable(false);

    try {
      const reader = await window.electronAPI.cards.checkAvailability();
      setCardReaderAvailable(Boolean(reader?.available));
    } catch (error) {
      console.error('Failed to check card reader availability:', error);
      setCardReaderAvailable(false);
    }
  };

  const handleCheckIn = (checkOutDate: string, checkOutTime: string) => {
    setShowDetailModal(false);
    setShowCheckInForm(true);
  };

  const handleExtendStay = async (newCheckOutDate: string, newCheckOutTime: string) => {
    if (!selectedRoom) return;

    const ok = await confirm({
      title: `Produžiti boravak — Soba ${selectedRoom.room_number}?`,
      message: `Novi datum odjave: ${newCheckOutDate} u ${newCheckOutTime}h`,
      confirmLabel: 'Produži boravak',
    });
    if (!ok) return;

    try {
      // KRITIČNO: Prvo ažuriraj PIN expiry na RPI/UL kontroleru!
      const [year, month, day] = newCheckOutDate.split('-');
      const expiryDateFormatted = `${day}.${month}.${year}`; // DD.MM.YYYY
      
      await window.electronAPI.rooms.setPin(selectedRoom.room_number, {
        pin: selectedRoom.guest_pin!,  // Koristi postojeći PIN
        expiry_date: expiryDateFormatted,
        expiry_time: newCheckOutTime,
        language: (((selectedRoom as any).language as 'srb' | 'eng' | 'ger' | undefined) || 'srb'),
        day_temp: selectedRoom.guest_in_temp || 22,
        night_temp: selectedRoom.guest_out_temp || 18,
      });

      // Pronađi aktivnog gosta u lokalnoj bazi
      const guests = await window.electronAPI.database.guests.getActive();
      const guest = guests.find((g: any) => g.room_number === selectedRoom.room_number);
      
      if (guest) {
        // Update checkout datetime u lokalnoj bazi
        const checkOutDateTime = `${newCheckOutDate} ${newCheckOutTime}:00`;
        await window.electronAPI.database.guests.update(guest.id!, {
          ...guest,
          check_out: checkOutDateTime
        });
      }

      // Kreiraj log zapis
      await window.electronAPI.database.systemLogs.create({
        room_number: selectedRoom.room_number,
        event_type: 'EXTEND_STAY',
        description: `Produžen boravak do ${newCheckOutDate} ${newCheckOutTime}h`,
        user_role: 'RECEPTION',
      });

      toast.success(`Boravak produžen do ${newCheckOutDate} u ${newCheckOutTime}h`);
      setShowDetailModal(false);
      fetchRooms();
    } catch (error) {
      console.error('Produženje boravka neuspješno:', error);
      toast.error('Greška: ' + (error as Error).message);
    }
  };

  const handleCheckOut = async () => {
    if (!selectedRoom) return;

    const ok = await confirm({
      title: `Check-out — Soba ${selectedRoom.room_number}?`,
      message: 'Gost će biti odjavljen, a PIN uklonjen sa sobe.',
      confirmLabel: 'Check-out',
      destructive: true,
    });
    if (!ok) return;

    try {
      // Delete PIN from room
      await window.electronAPI.rooms.deletePin(selectedRoom.room_number);

      // Update guest in database
      const guests = await window.electronAPI.database.guests.getActive();
      const guest = guests.find((g: any) => g.room_number === selectedRoom.room_number);
      
      if (guest) {
        await window.electronAPI.database.guests.checkOut(guest.id!);
      }

      // Create log entry
      await window.electronAPI.database.logs.create({
        room_number: selectedRoom.room_number,
        event_type: 'check_out',
        description: `Guest checked out from Room ${selectedRoom.room_number}`,
      });

      toast.success('Gost je uspješno odjavio!');
      setShowDetailModal(false);
      fetchRooms();
    } catch (error) {
      console.error('Check-out failed:', error);
      toast.error('Check-out neuspješan: ' + (error as Error).message);
    }
  };

  const handleCheckInSuccess = () => {
    fetchRooms();
  };

  const handleProgramCard = async (checkOutDate: string, checkOutTime: string) => {
    if (!selectedRoom) return;

    const roomLanguage = (
      ((selectedRoom as any).language as 'srb' | 'eng' | 'ger' | undefined) || 'srb'
    );

    try {
      const result = await window.electronAPI.cards.writeGuestCard({
        roomNumber: selectedRoom.room_number,
        checkOutDate,
        checkOutTime,
        language: roomLanguage,
      });

      if (!result?.ok) {
        toast.error(`Programiranje kartice neuspješno: ${result?.message || 'Nepoznata greška'}`);
        return;
      }

      await window.electronAPI.database.systemLogs.create({
        room_number: selectedRoom.room_number,
        event_type: selectedRoom.guest_pin ? 'EXTEND_STAY' : 'CHECK_IN',
        description: `Kartica upisana za sobu ${selectedRoom.room_number}, važi do ${checkOutDate} ${checkOutTime}`,
        user_role: 'RECEPTION',
      });

      toast.success(`Kartica uspješno programirana za sobu ${selectedRoom.room_number} (do ${checkOutDate} ${checkOutTime})`);
    } catch (error) {
      console.error('Card programming failed:', error);
      toast.error('Greška pri programiranju kartice');
    }
  };

  const handleSOSBannerClick = (room: Room) => {
    setSOSRoom(room);
    setShowSOSModal(true);
  };

  const handleSOSConfirm = async (room: Room) => {
    try {
      await window.electronAPI.rooms.resetSos(room.room_number);
      
      // Create system log
      await window.electronAPI.database.systemLogs.create({
        room_number: room.room_number,
        event_type: 'SOS_RESET',
        description: `SOS alarm resetovan za sobu ${room.room_number}`,
        user_role: 'RECEPTION',
      });

      // Refresh rooms to get updated SOS status
      fetchRooms();
    } catch (error) {
      console.error('Failed to reset SOS:', error);
      throw error;
    }
  };

  // Get stats for header
  // Prema toplik sys.txt:
  // - Slobodna = online, nema pina, nema kartice
  // - Zauzeta = postoji aktivan pin (check-in)
  // - Gost u sobi = kartica u odlagaču
  const stats = {
    total: rooms.length,
    available: rooms.filter((r) => r.online && !r.active_pin && !r.card_inserted).length,
    checkedIn: rooms.filter((r) => r.active_pin && !r.card_inserted).length,
    guestInRoom: rooms.filter((r) => r.card_inserted).length,
    offline: rooms.filter((r) => !r.online).length,
  };

  return (
    <div className="min-h-screen bg-background">
      {/* SOS Alert Banner - Fixed at top */}
      <SOSAlertBanner rooms={rooms} onRoomClick={handleSOSBannerClick} />

      {/* Header - Adjust padding if SOS banner is visible */}
      <header 
        className={`border-b border-border bg-card ${
          rooms.some(r => r.sos_active) ? 'mt-[72px]' : ''
        } sticky top-0 z-10 shadow-lg`}
      >
        <div className="container mx-auto px-4 py-4">
          <div className="flex justify-between items-center mb-4">
            <h1 className="text-3xl font-bold">Reception Dashboard</h1>
            <Button onClick={onLogout} variant="destructive">
              Logout
            </Button>
          </div>

          {/* Stats Bar */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="bg-background/50 p-3 rounded-lg">
              <div className="text-sm text-muted-foreground">Ukupno soba</div>
              <div className="text-2xl font-bold">{stats.total}</div>
            </div>
            <div className="bg-green-500/10 p-3 rounded-lg border border-green-500/30">
              <div className="text-sm text-green-400">🟢 Slobodne</div>
              <div className="text-2xl font-bold text-green-400">{stats.available}</div>
            </div>
            <div className="bg-blue-500/10 p-3 rounded-lg border border-blue-500/30">
              <div className="text-sm text-blue-400">🔵 Check-in</div>
              <div className="text-2xl font-bold text-blue-400">{stats.checkedIn}</div>
            </div>
            <div className="bg-red-500/10 p-3 rounded-lg border border-red-500/30">
              <div className="text-sm text-red-400">🔴 Gost u sobi</div>
              <div className="text-2xl font-bold text-red-400">{stats.guestInRoom}</div>
            </div>
            <div className="bg-gray-500/10 p-3 rounded-lg border border-gray-500/30">
              <div className="text-sm text-gray-400">⚠️ Offline</div>
              <div className="text-2xl font-bold text-gray-400">{stats.offline}</div>
            </div>
          </div>

          {/* Last Update */}
          <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
            <span>Last updated: {lastUpdate.toLocaleTimeString()}</span>
            <Button onClick={handleRefresh} variant="ghost" size="sm" disabled={isDiscovering}>
              {isDiscovering ? '🔍 Discovering...' : '🔄 Refresh'}
            </Button>
          </div>
        </div>
      </header>

      {/* Room Grid */}
      <main className="container mx-auto px-4 py-8">
        {loading || !initialized ? (
          <div className="text-center py-20">
            <div className="text-xl text-muted-foreground">Loading rooms...</div>
          </div>
        ) : rooms.length === 0 ? (
          <div className="text-center py-20">
            <div className="text-xl text-muted-foreground">No rooms found</div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {rooms.map((room) => (
              <RoomCard
                key={room.room_number}
                room={room}
                printerAvailable={printerAvailable}
                onClick={() => handleRoomClick(room)}
              />
            ))}
          </div>
        )}
      </main>

      {/* Room Detail Modal */}
      <RoomDetailModal
        room={selectedRoom}
        isOpen={showDetailModal}
        onClose={() => setShowDetailModal(false)}
        onCheckIn={handleCheckIn}
        onCheckOut={handleCheckOut}
        onExtendStay={handleExtendStay}
        onProgramCard={handleProgramCard}
        cardReaderAvailable={cardReaderAvailable}
      />

      {/* Check-In Form */}
      {selectedRoom && (
        <CheckInForm
          isOpen={showCheckInForm}
          onClose={() => setShowCheckInForm(false)}
          roomNumber={selectedRoom.room_number}
          onSuccess={handleCheckInSuccess}
          printerAvailable={printerAvailable}
        />
      )}

      {/* SOS Confirm Modal */}
      <SOSConfirmModal
        room={sosRoom}
        isOpen={showSOSModal}
        onClose={() => setShowSOSModal(false)}
        onConfirm={handleSOSConfirm}
      />
    </div>
  );
}
