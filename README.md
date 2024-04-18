# MolyuuOS RootFS Builder
This repository contains files for building whole MolyuuOS. Keep in mind this project is still working in progress, there are still lots of unresolved issues.

# Requirements
* Host OS: Arch Linux
* Dependencies: base-devel libarchive arch-install-scripts pikaur

# Build Guide
1. Build Local Repository

Currently we do not provide repository, you need to build all packages yourself, simply run command:

```shell
make repo
```

2. Build RootFS

Build Root File System via command below:

```shell
make image
```

A tarball contains MolyuuOS rootfs will save as `output/rootfs.tar.gz` if build success.

# Installation Guide
You will need an Arch Linux live-cd enviroment for a clean installation, but if you are a SteamOS-BTRFS user, you can simply install it to your home partition.

## 1. SteamOS-BTRFS User Installation GUIDE
This method will keep your SteamOS RootFS, you can switch back to SteamOS in anytime you want.

### 1.1 Create a subvolume for MolyuuOS
First, you will need to mount your home partiton for subvolume creation via command below, in my Steam Deck, the home partition is `/dev/nvme0n1p8`, but if you have modified your Steam Deck partition table, you might need to check which one is your home partiton via `sudo fdisk -l`.
```shell
sudo mount /dev/nvme0n1p8 /mnt
```

After you have mount your home partiton, create subvolume via command below:
```shell
sudo btrfs subvolume create /mnt/@molyuuos
```

Then umount it to prepare for next step:
```shell
sudo umount /mnt
```

### 1.2 Extract RootFS
First, you need to mount the subvolume you just created:
```shell
sudo mount /dev/nvme0n1p8 -o compress=zstd,subvol=/@molyuuos /mnt
```

Then simply extract the rootfs tarball with command:
```shell
sudo bsdtar --acls --xattrs -xpzf /path/to/rootfs.tar.gz -C /mnt
```

### 1.3 Post Install Configuration
First, mount ESP Partition to new rootfs:
```shell
sudo mkdir -p /mnt/boot/efi
sudo mount /dev/nvme0n1p1 /mnt/boot/efi
```

If you want to share your home floder between SteamOS and MolyuuOS (This can keep your games, but might break your KDE Desktop configuration, reset them if you are facing any problem), just mount it to new rootfs:
```shell
sudo rm -rf /mnt/home/*
sudo mount /dev/nvme0n1p8 -o compress=zstd,subvol=/@ /mnt/home
```

**BE ATTENTION** for user who don't want to share home partiton: For user who share home partition between two systems, MolyuuOS can directly use swap file which is created by SteamOS, so they may don't need any modification on it, but if you don't want to share, you'll need to manually configure it.

Then generate `fstab`:
```shell
sudo /bin/bash -c "genfstab -U /mnt > /mnt/etc/fstab"
```
**For User who don't want to share home partition**: Edit `fstab` and remove the line about Swap File.

### 1.4 Install a Bootloader
You can choose any bootloader you like (Read ArchWiki), here we use `grub` as our bootloader, first we enter `arch-chroot` environment:
```shell
sudo arch-chroot /mnt
```

Then install `grub`
```shell
sudo pacman -Sy grub efibootmgr
```

Initialize GRUB via command below:
```shell
grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=MolyuuOS
```

Generate Boot Config:
```shell
grub-mkconfig -o /boot/grub/grub.cfg
```

### 1.5 After all
Exit `arch-chroot` environment:
```shell
exit
```

Then umount RootFS:
```shell
sudo umount -R /mnt
```

After all, simply reboot your Steam Deck, and it will automatically boot into MolyuuOS. If you want to go back to SteamOS, enter UEFI Firmware Menu, the boot via Boot Menu.

## 2. Clean Install
You can read ArchWiki for installation guide, we don't need to use `pacstrap` to bootstrap system, just simply extract rootfs tarball for bootstrap, then follow the ArchWiki for post-installation guide.

# Known Issues

* Steam Built-in Virtual Keyboard does not support i18n on MolyuuOS, need work to find out why