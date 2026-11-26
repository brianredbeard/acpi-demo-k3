%{!?kernel_release:%global kernel_release 6.12.0-284.acpidebug.1.el10.riscv64}
%global kdir /usr/src/kernels/%{kernel_release}
%global moddir /lib/modules/%{kernel_release}/updates/k3
%global debug_package %{nil}

Name:           kmod-rfkill-gpio
Version:        1
Release:        1.%{lua:print((rpm.expand("%{kernel_release}"):gsub("-", "_")))}
Summary:        GPIO rfkill driver with PRP0001 property support
License:        GPL-2.0-or-later
ExclusiveArch:  riscv64
BuildRequires:  gcc, make, patch, kmod
BuildRequires:  kernel-devel-uname-r = %{kernel_release}
Requires:       kernel-uname-r = %{kernel_release}
Requires(post): kmod
Requires(postun): kmod
Source0:        rfkill-gpio.tar.gz
Patch0:         k3-rfkill-gpio-prp0001.patch

%description
%{summary}, built for %{kernel_release}.

%prep
%setup -q -c
%patch -P 0 -p1

%build
grep -Fxq 'CONFIG_RFKILL_GPIO=m' %{kdir}/.config || {
    echo 'This job needs CONFIG_RFKILL_GPIO=m in the target kernel.' >&2
    exit 1
}
cd net/rfkill
echo 'obj-m := rfkill-gpio.o' > Kbuild
make %{?_smp_mflags} -C %{kdir} M="$PWD" modules

%check
test "$(modinfo -F vermagic net/rfkill/rfkill-gpio.ko | cut -d' ' -f1)" = "%{kernel_release}"

%install
install -Dpm 0644 net/rfkill/rfkill-gpio.ko %{buildroot}%{moddir}/rfkill-gpio.ko

%post
/usr/sbin/depmod -a %{kernel_release}

%postun
if [ -d /lib/modules/%{kernel_release} ]; then
    /usr/sbin/depmod -a %{kernel_release}
fi

%files
%{moddir}/rfkill-gpio.ko
