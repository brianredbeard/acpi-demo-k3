%{!?kernel_release:%global kernel_release 6.12.0-284.acpidebug.1.el10.riscv64}
%global kdir /usr/src/kernels/%{kernel_release}
%global moddir /lib/modules/%{kernel_release}/updates/k3
%global debug_package %{nil}

Name:           kmod-ufs-spacemit
Version:        1
Release:        1.%{lua:print((rpm.expand("%{kernel_release}"):gsub("-", "_")))}
Summary:        SpacemiT UFS host driver with ACPI platform support
License:        GPL-2.0-only
ExclusiveArch:  riscv64
BuildRequires:  gcc, make, patch, kmod
BuildRequires:  kernel-devel-uname-r = %{kernel_release}
Requires:       kernel-uname-r = %{kernel_release}
Requires(post): kmod
Requires(postun): kmod
Source0:        ufs-spacemit.tar.gz
Patch0:         k3-ufs-acpi-build5.patch

%description
%{summary}, built for %{kernel_release}.

%prep
%setup -q -c
%patch -P 0 -p1

%build
grep -Fxq 'CONFIG_SCSI_UFS_SPACEMIT=m' %{kdir}/.config || {
    echo 'This job needs CONFIG_SCSI_UFS_SPACEMIT=m in the target kernel.' >&2
    exit 1
}
cd drivers/ufs/host
echo 'obj-m := ufs-spacemit.o' > Kbuild
make %{?_smp_mflags} -C %{kdir} M="$PWD" modules

%check
test "$(modinfo -F vermagic drivers/ufs/host/ufs-spacemit.ko | cut -d' ' -f1)" = "%{kernel_release}"

%install
install -Dpm 0644 drivers/ufs/host/ufs-spacemit.ko %{buildroot}%{moddir}/ufs-spacemit.ko

%post
/usr/sbin/depmod -a %{kernel_release}

%postun
if [ -d /lib/modules/%{kernel_release} ]; then
    /usr/sbin/depmod -a %{kernel_release}
fi

%files
%{moddir}/ufs-spacemit.ko
