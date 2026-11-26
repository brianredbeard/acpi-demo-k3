%{!?kernel_release:%global kernel_release 6.12.0-284.acpidebug.1.el10.riscv64}
%global kdir /usr/src/kernels/%{kernel_release}
%global moddir /lib/modules/%{kernel_release}/updates/k3
%global debug_package %{nil}

Name:           kmod-k3_tsensor
Version:        1
Release:        1.%{lua:print((rpm.expand("%{kernel_release}"):gsub("-", "_")))}
Summary:        SpacemiT K3 thermal sensor with ACPI thermal zones
License:        GPL-2.0-only
ExclusiveArch:  riscv64
BuildRequires:  gcc, make, patch, kmod
BuildRequires:  kernel-devel-uname-r = %{kernel_release}
Requires:       kernel-uname-r = %{kernel_release}
Requires(post): kmod
Requires(postun): kmod
Source0:        k3_tsensor.tar.gz
Patch0:         k3-tsensor-acpi-zones.patch

%description
%{summary}, built for %{kernel_release}.

%prep
%setup -q -c
%patch -P 0 -p1

%build
grep -Fxq 'CONFIG_SPACEMIT_K3_TSENSOR=m' %{kdir}/.config || {
    echo 'This job needs CONFIG_SPACEMIT_K3_TSENSOR=m in the target kernel.' >&2
    exit 1
}
cd drivers/thermal/spacemit
echo 'obj-m := k3_tsensor.o' > Kbuild
make %{?_smp_mflags} -C %{kdir} M="$PWD" modules

%check
test "$(modinfo -F vermagic drivers/thermal/spacemit/k3_tsensor.ko | cut -d' ' -f1)" = "%{kernel_release}"

%install
install -Dpm 0644 drivers/thermal/spacemit/k3_tsensor.ko %{buildroot}%{moddir}/k3_tsensor.ko

%post
/usr/sbin/depmod -a %{kernel_release}

%postun
if [ -d /lib/modules/%{kernel_release} ]; then
    /usr/sbin/depmod -a %{kernel_release}
fi

%files
%{moddir}/k3_tsensor.ko
