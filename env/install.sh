#!/usr/bin/env bash
CURRENT_USER="${SUDO_USER:-${USER:-$(id -un)}}"
CURRENT_HOME="$(getent passwd "$CURRENT_USER" | cut -d: -f6)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PRINTER_DATA_DIR="${CURRENT_HOME}/printer_data"
CONFIG_DIR="${PRINTER_DATA_DIR}/config"
KLIPPY_ENV="${CURRENT_HOME}/klippy-env"
REQUIREMENTS_FILE="${REPO_ROOT}/scripts/klippy-requirements.txt"
DATA_ZIP_SRC="${REPO_ROOT}/env/data.zip"
DATA_ZIP_DST="/usr/data.zip"
SOURCE_CONFIG_DIR="${REPO_ROOT}/env/config"
KLIPPER_SERVICE_FILE="/etc/systemd/system/klipper.service"

if [ -z "${CURRENT_HOME}" ] || [ ! -d "${CURRENT_HOME}" ]; then
  echo "Error: Could not determine the home directory for user ${CURRENT_USER}." >&2
  exit 1
fi

if [ ! -d "${SOURCE_CONFIG_DIR}" ]; then
  echo "Error: source config directory was not found: ${SOURCE_CONFIG_DIR}" >&2
  exit 1
fi

if [ ! -f "${REQUIREMENTS_FILE}" ]; then
  echo "Error: requirements file was not found: ${REQUIREMENTS_FILE}" >&2
  exit 1
fi

echo "Current user: ${CURRENT_USER}"
echo "User home directory: ${CURRENT_HOME}"

sudo -u "${CURRENT_USER}" mkdir -p \
  "${PRINTER_DATA_DIR}" \
  "${PRINTER_DATA_DIR}/certs" \
  "${PRINTER_DATA_DIR}/comms" \
  "${CONFIG_DIR}" \
  "${PRINTER_DATA_DIR}/database" \
  "${PRINTER_DATA_DIR}/gcodes" \
  "${PRINTER_DATA_DIR}/logs" \
  "${PRINTER_DATA_DIR}/misc" \
  "${PRINTER_DATA_DIR}/systemd"

echo "Created printer_data directory"
chmod -R 777 "${PRINTER_DATA_DIR}"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

backup_if_exists() {
  local source_file="$1"
  local backup_name="$2"

  if [ -f "${source_file}" ]; then
    mv "${source_file}" "${CONFIG_DIR}/${backup_name}"
    echo "Backed up $(basename "${source_file}") to ${backup_name}"
  fi
}

if [ -f "${CONFIG_DIR}/gcode_macro.cfg" ] && \
   [ -f "${CONFIG_DIR}/printer_params.cfg" ] && \
   [ -f "${CONFIG_DIR}/sensorless.cfg" ]; then
  echo "Configuration files already exist."
else
  backup_if_exists "${CONFIG_DIR}/gcode_macro.cfg" "gcode_macro_bak${TIMESTAMP}.cfg"
  backup_if_exists "${CONFIG_DIR}/printer_params.cfg" "printer_params_bak${TIMESTAMP}.cfg"
  backup_if_exists "${CONFIG_DIR}/sensorless.cfg" "sensorless_bak${TIMESTAMP}.cfg"
  backup_if_exists "${CONFIG_DIR}/printer.cfg" "printer_bak${TIMESTAMP}.cfg"

  sudo -u "${CURRENT_USER}" cp "${SOURCE_CONFIG_DIR}/gcode_macro.cfg" "${CONFIG_DIR}/gcode_macro.cfg"
  sudo -u "${CURRENT_USER}" cp "${SOURCE_CONFIG_DIR}/printer_params.cfg" "${CONFIG_DIR}/printer_params.cfg"
  sudo -u "${CURRENT_USER}" cp "${SOURCE_CONFIG_DIR}/sensorless.cfg" "${CONFIG_DIR}/sensorless.cfg"
  sudo -u "${CURRENT_USER}" cp "${SOURCE_CONFIG_DIR}/printer.cfg" "${CONFIG_DIR}/printer.cfg"

  echo "Copy configuration files into ${CONFIG_DIR}"
fi

echo "Updating package index..."
sudo apt-get update

echo "Installing system dependencies..."
sudo apt-get install -y \
  virtualenv \
  python-dev-is-python3 \
  python3-pip \
  libffi-dev \
  build-essential \
  libncurses-dev \
  libusb-dev \
  avrdude \
  gcc-avr \
  binutils-avr \
  avr-libc \
  stm32flash \
  dfu-util \
  libnewlib-arm-none-eabi \
  gcc-arm-none-eabi \
  binutils-arm-none-eabi \
  libusb-1.0-0 \
  srecord \
  unzip

echo "Installing pyserial..."
sudo pip3 install pyserial

if [ ! -d "${KLIPPY_ENV}" ]; then
  echo "Creating klippy virtual environment..."
  sudo virtualenv -p python3 "${KLIPPY_ENV}"
else
  echo "Existing klippy virtual environment detected, skipping creation."
fi

echo "Updating klippy virtual environment ownership..."
sudo chown -R "${CURRENT_USER}:${CURRENT_USER}" "${KLIPPY_ENV}"

echo "Installing klippy Python dependencies..."
"${KLIPPY_ENV}/bin/pip" install -r "${REQUIREMENTS_FILE}"

if [ ! -f "${DATA_ZIP_SRC}" ]; then
  echo "Error: archive was not found: ${DATA_ZIP_SRC}" >&2
  exit 1
fi


if [ ! -d "/usr/data" ]; then
  echo "Creating /usr/data directory ..."
  sudo cp "${DATA_ZIP_SRC}" "${DATA_ZIP_DST}"
  cd /usr
  sudo unzip -o data.zip
  sudo chmod -R 777 /usr/data
  sudo rm -f /usr/data.zip
else
  echo "/usr/data already exists, skipping archive extraction."
fi

if [ ! -f "${KLIPPER_SERVICE_FILE}" ]; then
  echo "Creating klipper systemd service..."
  sudo tee "${KLIPPER_SERVICE_FILE}" >/dev/null <<EOF
[Unit]
Description=Starts klipper on startup
After=network.target

[Install]
WantedBy=multi-user.target

[Service]
Type=simple
User=${CURRENT_USER}
RemainAfterExit=yes
ExecStart=${KLIPPY_ENV}/bin/python ${REPO_ROOT}/klippy/klippy.py ${CONFIG_DIR}/printer.cfg -l ${PRINTER_DATA_DIR}/logs/klippy.log -a ${PRINTER_DATA_DIR}/comms/klippy.sock
Restart=always
RestartSec=10
EOF
else
  echo "klipper.service already exists."
fi

sudo systemctl daemon-reload
sudo systemctl enable klipper.service
sudo systemctl start klipper.service

echo "Klipper automated installation completed successfully."
