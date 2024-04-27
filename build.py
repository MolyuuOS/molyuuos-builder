import os
import sys
import json
import requests

def execute_command(command: str):
    if os.system(command) != 0:
        raise Exception(f"Failed to execute command: {command}")

class PacmanConfigBuilder:
    def __init__(self, use_repos: list):
        self.repos = use_repos
        with open("pacman/pacman.conf.base", "r", encoding="utf-8") as f:
            self.base_configurations = f.read()

    def build(self) -> str:
        append_configurations = ""
        for repo in self.repos:
            with open(f"pacman/{repo}.conf", "r", encoding="utf-8") as f:
                append_configurations += "\n"
                append_configurations += f.read()
                append_configurations += "\n"

        return self.base_configurations + append_configurations

class ScriptBuilder:
    def __init__(self):
        self.script_content = "#!/bin/bash\n"

    def build(self) -> str:
        return self.script_content
    
    def append(self, content: str):
        self.script_content += content
        self.script_content += "\n"


class MolyuuOSBuilder:
    def __init__(self, manifest: dict, mountpoint: str = None, automount: bool = True, package_rootfs: bool = True):
        self.username = manifest["username"]
        self.hostname = manifest["hostname"]
        self.locale = manifest["locale"]
        self.packages = manifest["packages"]
        self.service = manifest.get("services")
        self.appendconfig = manifest.get("appendconfig")
        self.replaceconfig = manifest.get("replaceconfig")
        self.repo_key = manifest.get("repo_key")
        self.mountpoint = mountpoint
        self.automount = automount
        self.package_rootfs = package_rootfs
        self.pacman_conf_builder = PacmanConfigBuilder(manifest["use_repos"])

    def build(self) -> bool:
        workdir = os.getcwd()
        mountpoint = self.mountpoint if self.mountpoint else f"{workdir}/workspace/mnt"

        # Build Local Packages if neccessary
        if "local" in self.packages.keys():
            if not os.path.exists(f"{workdir}/repo/workspace/output"):
                raise Exception("You must build repo first")
            
        # Create Workspace
        print("Creating Workspace")
        if not os.path.exists("workspace"):
            os.mkdir("workspace")
        else:
            os.system("rm -rf workspace")
            os.mkdir("workspace")

        # Create MountPoint and RootFs
        os.mkdir("workspace/mnt")
        os.mkdir("workspace/rootfs")

        # Mount RootFs
        if self.automount:
            print("Mounting RootFS, this might require authentication")
            execute_command(f"mount --bind {workdir}/workspace/rootfs {mountpoint}")

        # Generate pacman.conf with upstream repositories only
        upstream_only_pacman_conf = PacmanConfigBuilder(["upstream"]).build().replace("/etc/pacman.d/mirrorlist", f"{mountpoint}/etc/pacman.d/mirrorlist")
        with open("workspace/pacman.upstream.conf", "w", encoding="utf-8") as f:
            f.write(upstream_only_pacman_conf)

        # Bootstrap the system
        print("Bootstrapping the system")
        mirrorlist = requests.get("https://archlinux.org/mirrorlist/all/").text.replace("#Server", "Server")
        execute_command(f"mkdir -p {mountpoint}/etc/pacman.d")
        with open(f"{mountpoint}/etc/pacman.d/mirrorlist", "w", encoding="utf-8") as f:
            f.write(mirrorlist)
        execute_command(f"pacstrap -K -M -C {workdir}/workspace/pacman.upstream.conf {mountpoint}")

        # Generate pacman.conf with all repositories
        pacman_conf = self.pacman_conf_builder.build()
        with open(f"{mountpoint}/etc/pacman.conf", "w", encoding="utf-8") as f:
            f.write(pacman_conf)

        # Preprare local repository
        if "local" in self.packages.keys():
            # Copy local packages
            execute_command(f"mv {workdir}/repo/workspace/output {mountpoint}/molyuu_repo")

            # Clean up build cache
            execute_command(f"rm -rf {workdir}/repo/workspace/build")

        # Set Locale
        print("Setting locale")
        with open(f"{mountpoint}/etc/locale.gen", "r", encoding="utf-8") as f:
            locale_gen = f.read()

        for locale in self.locale["generate"]:
            locale_gen = locale_gen.replace(f"#{locale}", f"{locale}")
        
        with open(f"{mountpoint}/etc/locale.gen", "w", encoding="utf-8") as f:
            f.write(locale_gen)

        with open(f"{mountpoint}/etc/locale.conf", "w", encoding="utf-8") as f:
            lang = self.locale.get("lang")
            f.write(f"LANG={lang}")

        # Copy PGP Keys
        if self.repo_key is not None:
            execute_command(f"cp {workdir}/pgp_key.asc {mountpoint}/pgp_key.asc")

        # Generate initialize script
        init_script_builder = ScriptBuilder()
        init_script_builder.append("set -e")
        init_script_builder.append("set -x")

        # Locale Generation
        init_script_builder.append("locale-gen")

        # Pacman initialization
        init_script_builder.append("pacman-key --init")
        init_script_builder.append("pacman-key --populate")
        if self.repo_key is not None:
            init_script_builder.append("pacman-key -a pgp_key.asc")
            init_script_builder.append(f"pacman-key --lsign-key {self.repo_key}")

        init_script_builder.append("pacman -Syy --noconfirm")

        # Install packages
        package_install_list = " ".join(self.packages["install"])
        package_remove_list = " ".join(self.packages["remove"])
        init_script_builder.append(f"pacman -S {package_install_list} --noconfirm")
        init_script_builder.append(f"pacman -Rcs {package_remove_list} --noconfirm")

        # Enable/Disable Services
        if self.service is not None:
            system_services = self.service.get("system")
            user_services = self.service.get("user")
            if system_services is not None:
                if system_services.get("enable") is not None:
                    for service in system_services["enable"]:
                        init_script_builder.append(f"systemctl enable {service}")
                
                if system_services.get("disable") is not None:
                    for service in system_services["disable"]:
                        init_script_builder.append(f"systemctl disable {service}")
            
            if user_services is not None:
                if user_services.get("enable") is not None:
                    for service in user_services["enable"]:
                        init_script_builder.append(f"systemctl --global enable {service}")
                
                if user_services.get("disable") is not None:
                    for service in user_services["disable"]:
                        init_script_builder.append(f"systemctl --global disable {service}")

        # Disable root login
        init_script_builder.append("passwd --lock root")

        # Initialize User
        init_script_builder.append("groupadd -r autologin")
        init_script_builder.append(f"useradd -m {self.username} -G autologin,wheel")
        init_script_builder.append(f"echo '{self.username}:{self.username}' | chpasswd")

        # Set hostname
        init_script_builder.append(f"echo '{self.hostname}' > /etc/hostname")

        # Add sudo permissions
        init_script_builder.append("sed -i '/%wheel ALL=(ALL:ALL) ALL/s/^# //g' /etc/sudoers")
        init_script_builder.append(f"echo \"{self.username} ALL=(ALL) NOPASSWD: /usr/bin/dmidecode -t 11\" >/etc/sudoers.d/steam")
        
        # Download and add racing wheel udev rules
        init_script_builder.append("pushd /usr/lib/udev/rules.d")
        init_script_builder.append("curl -L -O https://raw.githubusercontent.com/berarma/oversteer/master/data/udev/99-fanatec-wheel-perms.rules")
        init_script_builder.append("curl -L -O https://raw.githubusercontent.com/berarma/oversteer/master/data/udev/99-logitech-wheel-perms.rules")
        init_script_builder.append("curl -L -O https://raw.githubusercontent.com/berarma/oversteer/master/data/udev/99-thrustmaster-wheel-perms.rules")
        init_script_builder.append("popd")

        # Force -steamdeck option in desktop mode to prevent constant steam updates
        init_script_builder.append("sed -i 's,Exec=/usr/bin/steam-runtime,Exec=/usr/bin/steam-runtime -steamdeck,' /usr/share/applications/steam.desktop")

        # Initialize molyuuctl
        init_script_builder.append("molyuuctl login set-manager lightdm")
        init_script_builder.append("molyuuctl session register -n desktop -s plasmax11 -l \"qdbus6 org.kde.Shutdown /Shutdown org.kde.Shutdown.logout\"")
        init_script_builder.append("molyuuctl session register -n plasma -s plasmax11 -l \"qdbus6 org.kde.Shutdown /Shutdown org.kde.Shutdown.logout\"")
        init_script_builder.append("molyuuctl session register -n steam -s gamescope-wayland")
        init_script_builder.append("molyuuctl session set-default steam")
        init_script_builder.append(f"molyuuctl login autologin enable --user {self.username}")

        # Cleanup image
        if "local" in self.packages.keys():
            init_script_builder.append("rm -rf /molyuu_repo")
            
        init_script_builder.append("rm -rf /var/cache/pacman/pkg/*")
        init_script_builder.append("rm -rf /var/log/pacman.log")
        init_script_builder.append("rm -rf /var/lib/pacman/sync/*")

        # Write init script
        init_script = init_script_builder.build()
        with open(f"{mountpoint}/init.sh", "w", encoding="utf-8") as f:
            f.write(init_script)

        # Set Permission for init script
        execute_command(f"chmod a+x {mountpoint}/init.sh")

        # Run init script
        execute_command(f"arch-chroot {mountpoint} /init.sh")

        # Remove init script
        execute_command(f"rm {mountpoint}/init.sh")

        # Remove PGP key
        execute_command(f"rm -f {mountpoint}/pgp_key.asc")

        # Append custom configs
        if self.appendconfig is not None:
            for config in self.appendconfig:
                path = config["path"]
                content = config["content"]
                execute_command(f"cat {content} >> {mountpoint}{path}")

        # Replace configs
        if self.replaceconfig is not None:
            for config in self.replaceconfig:
                path = config["path"]
                content = config["content"]
                execute_command(f"cat {content} > {mountpoint}{path}")

        # Package rootfs
        if self.package_rootfs:
            if os.path.exists("{workdir}/output"):
                execute_command(f"rm -rf {workdir}/output")
            os.mkdir(f"{workdir}/output")
            execute_command(f"cd {mountpoint} && bsdtar --acls --xattrs -cpvaf {workdir}/output/rootfs.tar.gz .")

        # Clean up workspace
        if self.automount:
            execute_command(f"umount -R -l {mountpoint}")

        execute_command(f"rm -rf workspace")
        return True
    
def main():
    mountpoint = None
    if len(sys.argv) == 3:
        if sys.argv[1] == "--install":
            mountpoint = sys.argv[2]
    elif len(sys.argv) != 1:
        print("Usage: build.py [--install <mountpoint>]")
        sys.exit(1)
        
    with open("manifest.json", "r") as f:
        manifest = json.load(f)
        
    if not mountpoint:
        builder = MolyuuOSBuilder(manifest)
        builder.build()
        print("MolyuuOS image created at: output/rootfs.tar.gz")
    else:
        builder = MolyuuOSBuilder(manifest, mountpoint, False, False)
        builder.build()
        print("MolyuuOS has been successfully installed")

if __name__ == "__main__":
    main()
