#include <SPI.h>
#include <mcp2515.h>

// --- Configuração ---
#define PIN_CS 10

MCP2515 mcp2515(PIN_CS);
struct can_frame rxFrame;

// buffer de recebimento SLCAN
char slcanBuf[32];
uint8_t slcanLen = 0;

// flag para sniff
bool canOpen = true;

void setup() {
  Serial.begin(115200);
  while (!Serial) {} // espera serial pronta

  SPI.begin();

  mcp2515.reset();
  
  if (mcp2515.setBitrate(CAN_500KBPS, MCP_8MHZ) != MCP2515::ERROR_OK) {
    Serial.println("Erro ao configurar bitrate para 500kbps");
    while (1);
  }
  
  // já coloca em modo normal (CAN “aberta” desde o boot)
  mcp2515.setNormalMode();
  Serial.println("SLCAN ready (500kbps)");
}

void loop() {
  // 1) Lida com UM caractere da serial, se disponível.
  // Usar 'if' em vez de 'while' garante que o loop não bloqueie aqui.
  if (Serial.available()) {
    char c = Serial.read();
    if (c == '\r' || c == '\n') { // Fim de comando
      if (slcanLen > 0) {
        slcanBuf[slcanLen] = '\0';
        parseSlcan(slcanBuf);
        slcanLen = 0;
      }
    } else {
      if (slcanLen + 1 < sizeof(slcanBuf)) {
        slcanBuf[slcanLen++] = toupper(c); // Converte para maiúsculas para facilitar
      }
    }
  }

  // 2) Tenta ler UM frame da CAN, se a interface estiver aberta.
  // Esta função já é rápida e não-bloqueante.
  if (canOpen && mcp2515.readMessage(&rxFrame) == MCP2515::ERROR_OK) {
    sendSlcanFrame(rxFrame);
  }
  
  // O loop() repete imediatamente, alternando entre checar Serial e checar CAN.
}

// Interpreta comandos SLCAN simples: C (close), O (open), t (transmit)
void parseSlcan(const char* cmd) {
  bool ack = true;

  switch (cmd[0]) {
    case 'O': // open
      canOpen = true;
      break;

    case 'C': // close
      canOpen = false;
      break;

    case 'T': // Transmit Extended (não implementado, mas reconhece)
    case 't': // Transmit Standard 11-bit
    {
      struct can_frame txFrame;
      // Exemplo: t1238AABBCCDDEEFF
      // ID: 3 hex (cmd+1), DLC: 1 hex (cmd+4), DADOS: 2*DLC hex (cmd+5)
      char idStr[4] = { cmd[1], cmd[2], cmd[3], '\0' };
      char dlcStr[2] = { cmd[4], '\0' };
      
      txFrame.can_id  = strtoul(idStr, nullptr, 16);
      txFrame.can_dlc = strtoul(dlcStr, nullptr, 16);
      
      const char* p = cmd + 5;
      for (uint8_t i = 0; i < txFrame.can_dlc && i < 8; i++) {
        char tmp[3] = { p[0], p[1], '\0' };
        txFrame.data[i] = strtoul(tmp, nullptr, 16);
        p += 2;
      }
      
      mcp2515.sendMessage(&txFrame);
      break;
    }

    default:
      // comando não reconhecido → NACK (Bell char)
      Serial.write('\a');
      ack = false;
      break;
  }

  if (ack) {
    Serial.write('\r'); // ACK (Carriage Return) para python-can
  }
}

// Formata e envia um frame recebido como SLCAN: t<ID:3><DLC:1><DATA:2*DLC>\r
void sendSlcanFrame(const struct can_frame& f) {
  // Apenas frames padrão (11-bit) por simplicidade
  if (f.can_id & CAN_EFF_FLAG) return; 

  char out[32];
  uint8_t pos = 0;

  out[pos++] = 't';
  sprintf(out + pos, "%03X", f.can_id & 0x7FF);
  pos += 3;
  
  sprintf(out + pos, "%1X", f.can_dlc & 0x0F);
  pos += 1;
  
  for (uint8_t i = 0; i < f.can_dlc; i++) {
    sprintf(out + pos, "%02X", f.data[i]);
    pos += 2;
  }
  
  out[pos++] = '\r';
  Serial.write((uint8_t*)out, pos);
}