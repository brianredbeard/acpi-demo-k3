%{!?kernel_release:%global kernel_release 6.12.0-284.rv.0.el10.riscv64}
%global kdir /usr/src/kernels/%{kernel_release}
%global moddir /lib/modules/%{kernel_release}/updates/k3
%global debug_package %{nil}

Name:           kmod-gpio-spacemit-k1
Version:        1
Release:        1.%{lua:print((rpm.expand("%{kernel_release}"):gsub("-", "_")))}
Summary:        SpacemiT GPIO controller with ACPI interrupt support
License:        GPL-2.0-only OR MIT
ExclusiveArch:  riscv64
BuildRequires:  gcc, make, patch, kmod
BuildRequires:  kernel-devel-uname-r = %{kernel_release}
Requires:       kernel-uname-r = %{kernel_release}
Requires(post): kmod
Requires(postun): kmod
Source0:        gpio-spacemit-k1.tar.gz
Patch0:         k3-gpio-acpi-v3.patch

%description
%{summary}, built for %{kernel_release}.

%prep
%setup -q -c
%patch -P 0 -p1

%build
grep -Fxq 'CONFIG_GPIO_SPACEMIT_K1=m' %{kdir}/.config || {
    echo 'This job needs CONFIG_GPIO_SPACEMIT_K1=m in the target kernel.' >&2
    exit 1
}
cd drivers/gpio
echo 'obj-m := gpio-spacemit-k1.o' > Kbuild
make %{?_smp_mflags} -C %{kdir} M="$PWD" modules

%check
test "$(modinfo -F vermagic drivers/gpio/gpio-spacemit-k1.ko | cut -d' ' -f1)" = "%{kernel_release}"

%install
install -Dpm 0644 drivers/gpio/gpio-spacemit-k1.ko %{buildroot}%{moddir}/gpio-spacemit-k1.ko

%post
/usr/sbin/depmod -a %{kernel_release}

%postun
if [ -d /lib/modules/%{kernel_release} ]; then
    /usr/sbin/depmod -a %{kernel_release}
fi

%files
%{moddir}/gpio-spacemit-k1.ko
