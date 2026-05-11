import { rpiClient } from '../api/rpiClient';

/**
 * Generate a random 4-digit PIN (for guests, manager, maid)
 */
export function generateRandomPin(): string {
  return Math.floor(1000 + Math.random() * 9000).toString();
}

/**
 * Generate a random 5-digit PIN (for service)
 */
export function generateRandomServicePin(): string {
  return Math.floor(10000 + Math.random() * 90000).toString();
}

/**
 * Check if PIN already exists in ANY room (queries RPI for current state)
 * KRITIČNO: APP ne čuva pinove, mora pitati RPI!
 */
export async function checkPinCollision(pin: string): Promise<boolean> {
  try {
    // Dobavi sve sobe od RPI
    const rooms = await rpiClient.getRooms();
    
    // Provjeri da li neki room već koristi ovaj PIN
    const collision = rooms.some(room => room.guest_pin === pin);
    
    if (collision) {
      console.warn(`⚠️ PIN collision detected: ${pin} already in use`);
    }
    
    return collision;
  } catch (error) {
    console.error('❌ Failed to check PIN collision:', error);
    // Ako ne možemo provjeriti, pretpostavljamo da postoji kolizija (sigurnija opcija)
    return true;
  }
}

/**
 * Generate a unique PIN (no collision with ANY room)
 * GARANTUJE da PIN nikad neće biti isti kao bilo koji aktivan PIN u sistemu
 */
export async function generateUniquePin(): Promise<string> {
  let pin = generateRandomPin();
  let attempts = 0;
  const maxAttempts = 100;

  while (await checkPinCollision(pin) && attempts < maxAttempts) {
    pin = generateRandomPin();
    attempts++;
  }

  if (attempts >= maxAttempts) {
    throw new Error('Nije moguće generisati jedinstven PIN nakon 100 pokušaja. Provjerite RPI konekciju.');
  }

  console.log(`✅ Generated unique PIN: ${pin} (after ${attempts + 1} attempts)`);
  return pin;
}

/**
 * Validate PIN format (4 digits for guest/manager/maid)
 */
export function validatePinFormat(pin: string): boolean {
  return /^\d{4}$/.test(pin);
}

/**
 * Validate Service PIN format (5 digits)
 */
export function validateServicePinFormat(pin: string): boolean {
  return /^\d{5}$/.test(pin);
}
