/************************************************************
  Magspoof V5
  Modified version by Eduardo Contreras
  for Electronic Cats

  Original code by Samy Kamk  r (http://samy.pl/magspoof/)

  This example demonstrates how to use Magspoof v3 by Electronic Cats
  https://github.com/ElectronicCats/magspoof

  Development environment specifics:
  IDE: Arduino 1.8.9
  Hardware Platform:
  Magspoof V4

  This code is beerware; if you see me (or any other Electronic Cats
  member) at the local, and you've found our code helpful,
  please buy us a round!
  Distributed as-is; no warranty is given.
*/


#define PINS_PORT 1
#define PIN_A_BIT 4
#define PIN_B_BIT 5

#define BUTTON_PIN 11      // Button pin number
#define LED 34             // LED pin number
#define CLOCK_US 200       // Clock pulse duration in microseconds

#define BETWEEN_ZERO 53 // 53 zeros between track1 & 2

#define TRACKS 2           // Number of magnetic tracks emulated
#define MAX 80             // Maximum length of each track

//This is a fairly large array, store it in external memory with keyword __xdata
__xdata char recvStr[MAX];
uint8_t recvStrPtr = 0;
bool stringComplete = false;
bool serialComplete = false;
uint16_t echoCounter = 0;

// tracks in RAM
char tracks[2][MAX] = {
  "%B123456781234567^LASTNAME/FIRST^YYMMSSSDDDDDDDDDDDDDDDDDDDDDDDDD?\0", // Track 1
  ";123456781234567=112220100000000000000?\0" // Track 2
};

char revTrack[41]; // Array to store reversed track data

int sublen[] = {
  32, 48, 48
};

int bitlen[] = {
  7, 5, 5
};

unsigned int curTrack = 0;
uint8_t dir;

// Function to blink an LED on a specific pin
void blink(uint8_t pin, int msdelay, int times) {
  for (uint8_t i = 0; i < times; i++) {
    digitalWrite(pin, HIGH);
    delay(msdelay);
    digitalWrite(pin, LOW);
    delay(msdelay);
  }
}

// send a single bit out
void playBit(int sendBit) {
  dir ^= 1;
  digitalWriteFast(PINS_PORT, PIN_A_BIT, dir);
  digitalWriteFast(PINS_PORT, PIN_B_BIT, !dir);
  delayMicroseconds(CLOCK_US);

  if (sendBit) {
    dir ^= 1;
    digitalWriteFast(PINS_PORT, PIN_A_BIT, dir);
    digitalWriteFast(PINS_PORT, PIN_B_BIT, !dir);
  }
  delayMicroseconds(CLOCK_US);

}

// when reversing
void reverseTrack(int track) {
  int i = 0;
  track--; // index 0
  dir = 0;

  while (revTrack[i++] != '\0');
  i--;
  while (i--)
    for (int j = bitlen[track] - 1; j >= 0; j--)
      playBit((revTrack[i] >> j) & 1);
}

// plays out a full track, calculating CRCs and LRC
void playTrack(int track) {
  int tmp, crc, lrc = 0;
  track--; // index 0
  dir = 0;

  // First put out a bunch of leading zeros.
  for (int i = 0; i < 25; i++)
    playBit(0);

  //
  for (int i = 0; tracks[track][i] != '\0'; i++)
  {
    crc = 1;
    tmp = tracks[track][i] - sublen[track];

    for (int j = 0; j < bitlen[track] - 1; j++)
    {
      crc ^= tmp & 1;
      lrc ^= (tmp & 1) << j;
      
      playBit(tmp & 1);
      tmp >>= 1;
    }
    playBit(crc);
  }
  
  // finish calculating and send last "byte" (LRC)
  tmp = lrc;
  crc = 1;
  
  for (int j = 0; j < bitlen[track] - 1; j++)
  {
    crc ^= tmp & 1;
    playBit(tmp & 1);
    tmp >>= 1;
  }
  playBit(crc);

  // if track 1, play 2nd track in reverse (like swiping back?)
  if (track == 0)
  {
    // if track 1, also play track 2 in reverse
    // zeros in between
    for (int i = 0; i < BETWEEN_ZERO; i++)
      playBit(0);

    // send second track in reverse
    reverseTrack(2);
  }

  // finish with 0's
  for (int i = 0; i < 5 * 5; i++)
    playBit(0);

  digitalWriteFast(PINS_PORT, PIN_A_BIT, LOW);
  digitalWriteFast(PINS_PORT, PIN_B_BIT, LOW);
}

// stores track for reverse usage later
void storeRevTrack(int track) {
  int i, tmp, crc, lrc = 0;
  track--; // index 0
  dir = 0;

  for (i = 0; tracks[track][i] != '\0'; i++)
  {
    crc = 1;
    tmp = tracks[track][i] - sublen[track];

    for (int j = 0; j < bitlen[track] - 1; j++)
    {
      crc ^= tmp & 1;
      lrc ^= (tmp & 1) << j;
      tmp & 1 ?
      (revTrack[i] |= 1 << j) :
      (revTrack[i] &= ~(1 << j));
      tmp >>= 1;
    }
    crc ?
    (revTrack[i] |= 1 << 4) :
    (revTrack[i] &= ~(1 << 4));
  }


  // finish calculating and send last "byte" (LRC)
  tmp = lrc;
  crc = 1;
  for (int j = 0; j < bitlen[track] - 1; j++)
  {
    crc ^= tmp & 1;
    tmp & 1 ?
    (revTrack[i] |= 1 << j) :
    (revTrack[i] &= ~(1 << j));
    tmp >>= 1;
  }
  crc ?
  (revTrack[i] |= 1 << 4) :
  (revTrack[i] &= ~(1 << 4));

  i++;
  revTrack[i] = '\0';
}

void s_print(char *s) {
  for (int i = 0; i < MAX ; i++) {
    USBSerial_print(s[i]);
    if (s[i] == '?')break;
  }
  USBSerial_println();
}

// Alternative function to control the operation based on input option
void play(int option){
  digitalWrite(LED, HIGH);

  switch(option){
  case 1:
    // Play track 1
    playTrack(1);
    digitalWrite(LED, LOW);
    USBSerial_println("MagSpoof activated");
    break;
  case 2:
    // Play track 2
    playTrack(2);
    digitalWrite(LED, LOW);
    USBSerial_println("MagSpoof activated");
    break;
  case 0:
    // Play alternating tracks on successive button presses
    playTrack(1 + (curTrack++ % 2));
    digitalWrite(LED, LOW);
    USBSerial_println("MagSpoof activated");
  }
}

// Setup function to initialize hardware and load data
void setup() {
  Serial0_begin(9600);

  delay(2000);
  
  pinMode(LED, OUTPUT);
  digitalWrite(LED, LOW);

  pinModeFast(PINS_PORT, PIN_A_BIT, OUTPUT);
  pinModeFast(PINS_PORT, PIN_B_BIT, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  //load track1 from eeprom

  USBSerial_println("EEPROM track 1:");

  for (uint8_t i = 0; i < MAX; i++) {
    char eepromData = eeprom_read_byte(i);
    tracks[0][i] = eepromData;
    USBSerial_print(tracks[0][i]);
    if (tracks[0][i] == '?') {
      tracks[0][i + 1] = '\0';
      break;
    }
  }

  //load track2 from eeprom
  USBSerial_println();
  USBSerial_println("EEPROM track 2:");
  
  for (uint8_t i = MAX; i < 2 * MAX; i++) {
    char eepromData = eeprom_read_byte(i);
    tracks[1][i - MAX] = eepromData;
    USBSerial_print(tracks[1][i - MAX]);
    if (tracks[1][i - MAX] == '?') {
      tracks[1][i + 1 - MAX] = '\0';
      break;
    }
  }

  storeRevTrack(TRACKS);

  USBSerial_println();
  USBSerial_flush();
  USBSerial_println("MAGSPOOF");
  USBSerial_println();
  USBSerial_println("h: Help");
  USBSerial_println();
}

// Main loop to handle button presses and USB serial commands
void loop() {
  if (digitalRead(BUTTON_PIN) == 0) {
    USBSerial_println("MagSpoof");
    digitalWrite(LED, HIGH);
    play(0);
    digitalWrite(LED, LOW);
    s_print(tracks[0]);
    s_print(tracks[1]);
  }
  
  // Handle incoming serial data
  while (Serial0_available()) {
    char serialChar = Serial0_read();
    USBSerial_write(serialChar);
    if ((serialChar == '\n') || (serialChar == '\r') ) {
      recvStr[recvStrPtr] = '\0';
      if (recvStrPtr > 0) {
        serialComplete = true;
        break;
      }
    } else {
      recvStr[recvStrPtr] = serialChar;
      recvStrPtr++;
      if (recvStrPtr == MAX) {
        recvStr[recvStrPtr] = '\0';
        digitalWrite(LED, HIGH);
        delay(50);
        digitalWrite(LED, LOW);
        serialComplete = true;
        break;
      }
    }
  }

  while (USBSerial_available()) {
    char serialChar = USBSerial_read();
    if ((serialChar == '\n') || (serialChar == '\r') ) {
      recvStr[recvStrPtr] = '\0';
      if (recvStrPtr > 0) {
        stringComplete = true;
        break;
      }
    } else {
      recvStr[recvStrPtr] = serialChar;
      recvStrPtr++;
      if (recvStrPtr == MAX) {
        recvStr[recvStrPtr] = '\0';
        stringComplete = true;
        break;
      }
    }
  }
  
  // Process complete strings from USB serial
  if (stringComplete || serialComplete) {

  // Store tracks in EEPROM
    if (recvStr[0] == 's') {

      USBSerial_println("...to EEPROM");
      for (uint8_t i = 0; i < MAX ; i++) {
        eeprom_write_byte(i, tracks[0][i]);
        if (tracks[0][i] == '?') {
          eeprom_write_byte(i + 1, '\0');
          tracks[0][i + 1] = '\0';
          break;
        }
      }

      for (uint8_t i = MAX; i < 2 * MAX ; i++) {
        eeprom_write_byte(i, tracks[1][i - MAX]);
        if (tracks[1][i] == '?') {
          eeprom_write_byte(i + 1, '\0');
          tracks[1][i + 1] = '\0';
          break;
        }
      }
      
      serialComplete = false;
      stringComplete = false;
      USBSerial_flush();  
    }

    if (recvStr[0] == '%') {
      for (uint8_t i = 0; i < MAX ; i++) {
        tracks[0][i] = recvStr[i];
        if (recvStr[i] == '?') {
          {
            tracks[0][i + 1] = '\0';
            break;
          }
        }
      }
      storeRevTrack(TRACKS);
    }

    if (recvStr[0] == ';') {
      for (uint8_t i = 0; i < MAX ; i++) {
        tracks[1][i] = recvStr[i];
        if (recvStr[i] == '?') {
          {
            tracks[1][i + 1] = '\0';
            break;
          }
        }
      }
      storeRevTrack(TRACKS);
    }

    // Play tracks in RAM
    if (recvStr[0] == 'p') {
      if(recvStr[1] == '1') {
      USBSerial_println();  
      USBSerial_print("PLAY TRACK 1");
      USBSerial_println();
      play(1);  
      }
      else if(recvStr[1] == '2') {
      USBSerial_println();  
      USBSerial_print("PLAY TRACK 2");
      USBSerial_println();
      play(2);   
      }
      else {
      USBSerial_println();  
      USBSerial_print("PLAY");
      USBSerial_println();
      play(0);
      }  
    }

  // Print tracks stored in RAM
  if (recvStr[0] == 'd') {   
    USBSerial_println();
    USBSerial_println("RAM TRACK 1:");
    s_print(tracks[0]);
    USBSerial_println("RAM TRACK 2:");
    s_print(tracks[1]);
    USBSerial_println();  
  }

  // Print help menu
  if (recvStr[0] == 'h') {
    USBSerial_println();
    USBSerial_println("Available commands:");
    USBSerial_println("h: Help (display this menu)");
    USBSerial_println("s: Save tracks from RAM to EEPROM");
    USBSerial_println("p1: Play track 1");
    USBSerial_println("p2: Play track 2");
    USBSerial_println("p: Play tracks alternating between 1 and 2");
    USBSerial_println("d: Display the contents of tracks in RAM");
    USBSerial_println();
  }

  recvStrPtr = 0;
  serialComplete = false;
  stringComplete = false;
  USBSerial_flush();  
  
 }
}
