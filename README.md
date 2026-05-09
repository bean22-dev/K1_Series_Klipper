# Introduce
This is clone from https://github.com/CrealityOfficial/K1_Series_Klipper.git.

The main MCU is FYSETC's CATALYST.K; the toolboard is FYSETC's 
Catalyst.K ToolHead(https://github.com/FYSETC/Catalyst.K_Kit), and the heated bed MCU is Creality's official leveling module(K1-MAX-L_V11).

# Raspberry Pi
## Hardware
Raspberry Pi 5/4/3 can be used. 

## Image and Tool
### Image
You must use the Debian 11 image. System image Download Link https://downloads.raspberrypi.org/raspios_lite_arm64/images/raspios_lite_arm64-2023-05-03/

### Tool
The download link for the Raspberry Pi image creation tool is https://github.com/raspberrypi/rpi-imager/releases?page=3. After downloading, proceed to complete the tool installation.

## Image Creation
* **Step 1:** \
Insert the SD card into the USB drive, and then insert the USB drive into the computer.

* **Step 2:** \
Open the image burning software.
<p align="center">
  <img src="env/image/image_software.png" width="320" height="240">
</p>

* **Step 3:** \
<p align="center">
  <img src="env/image/image_device.png" width="320" height="240">
</p>

* **Step 4:** \
<p align="center">
  <img src="env/image/image_system.png" width="320" height="240">
  <img src="env/image/image_custom.png" width="320" height="240">
  <img src="env/image/image_downloaded.png" width="320" height="240">
</p>

* **Step 5:** \
<p align="center">
  <img src="env/image/image_sd.png" width="320" height="240">
</p>


* **Step 6:** \
Click the Next button and click Edit Settings button.
<p align="center">
  <img src="env/image/image_next.png" width="320" height="240">
</p>

* **Step 7:** \
Configure the information for the General, Services, and Optional Services tabs, and then click save button.
<p align="center">
  <img src="env/image/image_general.png" width="320" height="240">
  <img src="env/image/image_service.png" width="320" height="240">
  <img src="env/image/image_option.png" width="320" height="240">
</p>


* **Step 7:** \
Click the YES button.
<p align="center">
  <img src="env/image/image_yes.png" width="320" height="240">
  <img src="env/image/image_yes1.png" width="320" height="240">
</p>

* **Step 8:** \
Waiting for image creation to complete.

# Software Install
Install additional software applications on the Raspberry Pi after remotely logging in via SSH using MobaXterm.

## Kiauh
* **Step 1:** \
  To download this script, it is necessary to have git installed. If you don't
  have git already installed, or if you are unsure, run the following command:

```shell
sudo apt-get update && sudo apt-get install git -y
```

* **Step 2:** \
  Once git is installed, use the following command to download KIAUH into your
  home-directory:

```shell
cd ~ && git clone https://github.com/dw-0/kiauh.git
```

## Klipper
* **Step 1:** \
use the following command to download K1_Series_Klipper into your home-directory:
```shell
cd ~ && git clone https://github.com/bean22-dev/K1_Series_Klipper.git
```

* **Step 2:** \
Use the following command to install automatically.
```shell
cd ~/K1_Series_Klipper/env && chmod +x install.sh && sudo ./install.sh
```

## Moonrake
* **Step 1:** \
run kiauh
```shell
cd ~ && ./kiauh/kiauh.sh
```

* **Step 2:** \
Select Moonraker under the Install menu.


## Mainsail
run kiauh and Select Mainsail under the Install menu.

## KlipperScreen
run kiauh and Select KlipperScreen under the Install menu.

## Crowsnest
run kiauh and Select Crowsnest under the Install menu.

# MCU fireware
## Catalyst.K
### config with no bootloader
```shell
cd ~/K1_Series_Klipper && make menuconfig
```
<p align="center">
  <img src="env/image/mainmcu_other.png" width="560" height="160">
  <img src="env/image/mainmcu_mcu.png" width="560" height="80">
  <img src="env/image/mainmcu_usb.png" width="560" height="80">
</p>

  ### dfu mode
    You need to enter DFU mode before you can compile and burn the firmware. As shown in the figure above,

    press and hold BOOT0,
    press the RESET button for one second,
    release RESET,
    wait for 3 seconds,
    release BOOT0.
  ### flash fireware
  use the following command to download K1_Series_Klipper into your home-directory:
```shell
cd ~/K1_Series_Klipper && make flash FLASH_DEVICE=0483:df11
```
you will see "File downloaded successfully".

## Catalyst.K ToolHead
  ### config with no bootloader
```shell
cd ~/K1_Series_Klipper && make menuconfig
```
<p align="center">
  <img src="env/image/toolhead_other.png" width="560" height="160">
  <img src="env/image/toolhead_mcu.png" width="560" height="80">
  <img src="env/image/toolhead_usb.png" width="560" height="80">
</p>

  ### dfu mode
    You need to enter DFU mode before you can compile and burn the firmware. As shown in the figure above,

    press and hold BOOT0,
    press the RESET button for one second,
    release RESET,
    wait for 3 seconds,
    release BOOT0.
  ### flash fireware
  use the following command to download K1_Series_Klipper into your home-directory:
```shell
cd ~/K1_Series_Klipper && make flash FLASH_DEVICE=0483:df11
```
you will see "File downloaded successfully".

## level mcu
  SERIAL mode is the only operating mode.
  ### config with bootloader
  use the following command to run config tool:
```shell
cd ~/K1_Series_Klipper && make menuconfig
```
<p align="center">
  <img src="env/image/bed_other.png" width="560" height="160">
  <img src="env/image/bed_mcu.png" width="560" height="80">
</p>

  ### bootloader mode
  disconnect and then reconnect the leveling MCU terminal.
  <p align="center">
  <img src="env/image/bed_poweron.png" width="320" height="320">
</p>

  ### flash fireware
Execute the following command within 15 seconds of the leveling MCU powering back on.
```shell
systemctl stop klipper && sleep 1 && cd ~/K1_Series_Klipper/env && python3 mcu_util.py -c -i /dev/serial/by-id/usb-wch.cn_USB_Dual_Serial_0123456789-if02 -u -f ~/K1_Series_Klipper/out/klipper.bin -v && systemctl start klipper
```