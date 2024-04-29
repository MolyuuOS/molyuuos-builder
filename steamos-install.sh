#!/bin/bash

set -e

SCRIPT="$0"
HOME_PARTITION_DEVICE="/dev/disk/by-partsets/shared/home"
ESP_PARTITION_DEVICE="/dev/disk/by-partsets/shared/esp"
MOLYUUOS_BUILDER_REPOSITORY="https://github.com/MolyuuOS/molyuuos-builder.git"
MOLYUUOS_ROOTFS_MOUNTPOINT="/tmp/molyuuos_rootfs"
MOLYUUOS_ROOTFS_SUBVOL_NAME="@molyuuos"
MOLYUUOS_UNSHARED_HOME_SUBVOL_NAME="@molyuuos_home"
MOLYUUOS_USE_SHARED_HOME="false"
USER_PASSWORD=""

function check_requirement() {
    if [[ $(lsb_release -s -i) != "SteamOS" ]]; then
        kdialog --error "This script can only be run on SteamOS"
        exit -1
    fi

    if [[ $(lsblk -no FSTYPE $HOME_PARTITION_DEVICE) != "btrfs" ]]; then
        kdialog --error "You must convert your home partition to BTRFS via SteamOS-BTRFS first."
        exit -1
    fi
}

function run_as_root() {
    if [[ $EUID != 0 ]]; then
        if $(passwd -S $(whoami) | grep -q " P "); then
            USER_PASSWORD=$(kdialog --password "Please enter user $(whoami)'s password:")
            if ! (echo "$USER_PASSWORD" | sudo -S true > /dev/null 2>&1); then
                kdialog --error "Password incorrect!"
                exit -1
            fi
        else
            USER_PASSWORD=$(kdialog --password "Please set a password for user $(whoami):")
            if [[ $(kdialog --password "Please enter password again:") != $USER_PASSWORD ]]; then
                kdialog --error "Password not match!"
                exit -1
            fi
            echo "$USER_PASSWORD"
            if ! (yes "$USER_PASSWORD" | passwd $(whoami)); then
                kdialog --error "Failed to set password"
                exit -1
            fi
        fi
        echo $USER_PASSWORD | exec sudo -S $SCRIPT
    fi
}

function prepare_rootfs() {
    if ! [[ -d $MOLYUUOS_ROOTFS_MOUNTPOINT ]]; then
        mkdir -p $MOLYUUOS_ROOTFS_MOUNTPOINT
    fi
    mount $HOME_PARTITION_DEVICE $MOLYUUOS_ROOTFS_MOUNTPOINT
    if [[ -d $MOLYUUOS_ROOTFS_MOUNTPOINT/@molyuuos ]]; then
        umount $MOLYUUOS_ROOTFS_MOUNTPOINT
        kdialog --error "MolyuuOS RootFS found! Is MolyuuOS already installed?"
        exit -1
    fi
    
    # Create and mount subvolume for MolyuuOS
    if kdialog --yesno "Do you want to use the SteamOS Home as the Home for a new installation of MolyuuOS?" ; then
        MOLYUUOS_USE_SHARED_HOME="true"
    fi
    btrfs subvolume create $MOLYUUOS_ROOTFS_MOUNTPOINT/$MOLYUUOS_ROOTFS_SUBVOL_NAME
    if [[ $MOLYUUOS_USE_SHARED_HOME == "false" ]]; then
        btrfs subvolume create $MOLYUUOS_ROOTFS_MOUNTPOINT/$MOLYUUOS_UNSHARED_HOME_SUBVOL_NAME
    fi
    umount $MOLYUUOS_ROOTFS_MOUNTPOINT
    mount $HOME_PARTITION_DEVICE -o compress=zstd,subvol=/$MOLYUUOS_ROOTFS_SUBVOL_NAME $MOLYUUOS_ROOTFS_MOUNTPOINT

    # Create home and esp mount point
    mkdir -p $MOLYUUOS_ROOTFS_MOUNTPOINT/boot/efi
    mkdir -p $MOLYUUOS_ROOTFS_MOUNTPOINT/home

    # Mount esp and home
    mount $ESP_PARTITION_DEVICE $MOLYUUOS_ROOTFS_MOUNTPOINT/boot/efi
    if [[ $MOLYUUOS_USE_SHARED_HOME == "true" ]]; then
        mount $HOME_PARTITION_DEVICE -o compress=zstd,subvol=/@ $MOLYUUOS_ROOTFS_MOUNTPOINT/home
    else
        mount $HOME_PARTITION_DEVICE -o compress=zstd,subvol=/$MOLYUUOS_UNSHARED_HOME_SUBVOL_NAME $MOLYUUOS_ROOTFS_MOUNTPOINT/home
    fi
}

function install_molyuuos() {
    # Bootstrap Keyrings
    steamos-readonly disable
    pacman-key --init
    pacman-key --populate archlinux
    pacman-key --populate holo
    pacman -Sy python-requests --noconfirm
    steamos-readonly enable

    # Install MolyuuOS
    if [[ -d /tmp/molyuuos_builder ]]; then
        rm -rf /tmp/molyuuos_builder
    fi
    git clone --depth=1 $MOLYUUOS_BUILDER_REPOSITORY /tmp/molyuuos_builder
    CURRENT_WORKSPACE="$PWD"
    if ! (cd /tmp/molyuuos_builder && python -u build.py --install $MOLYUUOS_ROOTFS_MOUNTPOINT); then
        umount -R $MOLYUUOS_ROOTFS_MOUNTPOINT
        kdialog --error "Failed to install MolyuuOS!"
    fi

    # Generate fstab
    genfstab -U $MOLYUUOS_ROOTFS_MOUNTPOINT > $MOLYUUOS_ROOTFS_MOUNTPOINT/etc/fstab

    # Install GRUB
    arch-chroot $MOLYUUOS_ROOTFS_MOUNTPOINT grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=MolyuuOS
    arch-chroot $MOLYUUOS_ROOTFS_MOUNTPOINT grub-mkconfig -o /boot/grub/grub.cfg

    # Setup Plymouth
    board_name=$(cat /sys/class/dmi/id/board_name)
    if [[ $board_name = "Galileo" ]]; then
        cd $MOLYUUOS_ROOTFS_MOUNTPOINT/usr/share/plymouth/themes/steamos && ln -s steamos-galileo.png steamos.png
    else
        cd $MOLYUUOS_ROOTFS_MOUNTPOINT/usr/share/plymouth/themes/steamos && ln -s steamos-jupiter.png steamos.png
    fi
    arch-chroot $MOLYUUOS_ROOTFS_MOUNTPOINT plymouth-set-default-theme -R steamos

    # Cleanup and finish installation
    cd "$CUURENT_WORKSPACE"
    rm -rf /tmp/molyuuos_builder
    umount -R -l $MOLYUUOS_ROOTFS_MOUNTPOINT
    rm -rf $MOLYUUOS_ROOTFS_MOUNTPOINT
}

check_requirement
run_as_root
prepare_rootfs
install_molyuuos

if kdialog --yesno "MolyuuOS has been successfully installed, do you want to restart now?" ; then
    reboot
fi