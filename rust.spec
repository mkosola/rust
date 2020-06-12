# Combined rust / cross-{arch}-rust) specfile
Name: rust
# Keep Name on top !

%global rustc_version 1.44.0
%global cargo_version 1.44.0
# %global rust_triple arm-unknown-linux-gnueabi
# %global rust_triple i686-unknown-linux-gnu
%global rust_triple armv7-unknown-linux-gnueabihf

Version:        %{rustc_version}
Release:        1
Summary:        The Rust Programming Language
License:        (ASL 2.0 or MIT) and (BSD and MIT)
URL:            https://www.rust-lang.org
# ExclusiveArch:  %{ix86}

%global rustc_package rustc-%{rustc_version}-src
Source0:        https://static.rust-lang.org/dist/rustc-%{rustc_version}-src.tar.gz
Source1:        https://static.rust-lang.org/dist/rust-%{rustc_version}-%{rust_triple}.tar.gz

Patch1: 0001-Use-a-non-existent-test-path-instead-of-clobbering-d.patch

%global bootstrap_root rust-%{rustc_version}-%{rust_triple}
%global local_rust_root %{_builddir}/%{bootstrap_root}/usr
%global bootstrap_source rust-%{rustc_version}-%{rust_triple}.tar.gz

BuildRequires:  gcc-c++
BuildRequires:  ncurses-devel
BuildRequires:  curl
BuildRequires:  pkgconfig(libcurl)
BuildRequires:  pkgconfig(liblzma)
BuildRequires:  pkgconfig(openssl)
BuildRequires:  pkgconfig(zlib)
BuildRequires:  python
BuildRequires:  llvm-devel
BuildRequires:  libffi-devel

Requires:       %{name}-std-static = %{rustc_version}-%{release}
Requires:       /usr/bin/cc

# ALL Rust libraries are private, because they don't keep an ABI.
%global _privatelibs lib(.*-[[:xdigit:]]{16}*|rustc.*)[.]so.*
%global __provides_exclude ^(%{_privatelibs})$
%global __requires_exclude ^(%{_privatelibs})$
%global __provides_exclude_from ^(%{_docdir}|%{rustlibdir}/src)/.*$
%global __requires_exclude_from ^(%{_docdir}|%{rustlibdir}/src)/.*$

# While we don't want to encourage dynamic linking to Rust shared libraries, as
# there's no stable ABI, we still need the unallocated metadata (.rustc) to
# support custom-derive plugins like #[proc_macro_derive(Foo)].  But eu-strip is
# very eager by default, so we have to limit it to -g, only debugging symbols.
%global _find_debuginfo_opts -g
%undefine _include_minidebuginfo

%global rustflags -Clink-arg=-Wl,-z,relro,-z,now

%description
Rust is a systems programming language that runs blazingly fast, prevents
segfaults, and guarantees thread safety.

This package includes the Rust compiler and documentation generator.


%package std-static
Summary:        Standard library for Rust

%description std-static
This package includes the standard libraries for building applications
written in Rust.


%package debugger-common
Summary:        Common debugger pretty printers for Rust
BuildArch:      noarch

%description debugger-common
This package includes the common functionality for %{name}-gdb and %{name}-lldb.


%package gdb
Summary:        GDB pretty printers for Rust
BuildArch:      noarch
Requires:       gdb
Requires:       %{name}-debugger-common = %{rustc_version}-%{release}

%description gdb
This package includes the rust-gdb script, which allows easier debugging of Rust
programs.


%package lldb
Summary:        LLDB pretty printers for Rust

Requires:       lldb
Requires:       python2-lldb
Requires:       %{name}-debugger-common = %{rustc_version}-%{release}

%description lldb
This package includes the rust-lldb script, which allows easier debugging of Rust
programs.


%package -n cargo
Summary:        Rust's package manager and build tool
Version:        %{cargo_version}

%description -n cargo
Cargo is a tool that allows Rust projects to declare their various dependencies
and ensure that you'll always get a repeatable build.

%prep

%setup -q -n %{bootstrap_root} -T -b 1
./install.sh --components=cargo,rustc,rust-std-%{rust_triple} \
  --prefix=%{local_rust_root} --disable-ldconfig
test -f '%{local_rust_root}/bin/cargo'
test -f '%{local_rust_root}/bin/rustc'

%setup -q -n %{rustc_package}
%patch1 -p1

rm -rf src/llvm/
rm -rf src/llvm-emscripten/

# We never enable other LLVM tools.
rm -rf src/tools/clang
rm -rf src/tools/lld
rm -rf src/tools/lldb


%build

export RUSTFLAGS="%{rustflags}"

# We're going to override --libdir when configuring to get rustlib into a
# common path, but we'll fix the shared libraries during install.
%global common_libdir %{_prefix}/lib
%global rustlibdir %{common_libdir}/rustlib

# full debuginfo is exhausting memory; just do libstd for now
# https://github.com/rust-lang/rust/issues/45854
%define enable_debuginfo --disable-debuginfo --disable-debuginfo-only-std --disable-debuginfo-tools --disable-debuginfo-lines

%configure --disable-option-checking \
  --libdir=%{common_libdir} \
  --build=%{rust_triple} --host=%{rust_triple} --target=%{rust_triple} \
  --local-rust-root=%{local_rust_root} \
  --enable-local-rebuild \
  --enable-llvm-link-shared \
  --enable-optimize \
  --disable-rpath \
  --disable-docs \
  --disable-compiler-docs \
  --disable-codegen-tests \
  %{enable_debuginfo} \
  --enable-vendor \
  --enable-extended \
  --tools=cargo \
  --llvm-root=/usr/

python ./x.py build


%install
export RUSTFLAGS="%{rustflags}"

DESTDIR=%{buildroot} python ./x.py install

# Make sure the shared libraries are in the proper libdir
%if "%{_libdir}" != "%{common_libdir}"
mkdir -p %{buildroot}%{_libdir}
find %{buildroot}%{common_libdir} -maxdepth 1 -type f -name '*.so' \
  -exec mv -v -t %{buildroot}%{_libdir} '{}' '+'
%endif

# The shared libraries should be executable for debuginfo extraction.
find %{buildroot}%{_libdir} -maxdepth 1 -type f -name '*.so' \
  -exec chmod -v +x '{}' '+'

# The libdir libraries are identical to those under rustlib/.  It's easier on
# library loading if we keep them in libdir, but we do need them in rustlib/
# to support dynamic linking for compiler plugins, so we'll symlink.
(cd "%{buildroot}%{rustlibdir}/%{rust_triple}/lib" &&
 find ../../../../%{_lib} -maxdepth 1 -name '*.so' |
 while read lib; do
   # make sure they're actually identical!
   cmp "$lib" "${lib##*/}"
   ln -v -f -s -t . "$lib"
 done)

# Remove installer artifacts (manifests, uninstall scripts, etc.)
find %{buildroot}%{rustlibdir} -maxdepth 1 -type f -exec rm -v '{}' '+'

# Remove backup files from %%configure munging
find %{buildroot}%{rustlibdir} -type f -name '*.orig' -exec rm -v '{}' '+'

# Remove unwanted documentation files
rm -f %{buildroot}%{_docdir}/%{name}/README.md
rm -f %{buildroot}%{_docdir}/%{name}/COPYRIGHT
rm -f %{buildroot}%{_docdir}/%{name}/LICENSE
rm -f %{buildroot}%{_docdir}/%{name}/LICENSE-APACHE
rm -f %{buildroot}%{_docdir}/%{name}/LICENSE-MIT
rm -f %{buildroot}%{_docdir}/%{name}/LICENSE-THIRD-PARTY
rm -f %{buildroot}%{_docdir}/%{name}/*.old

# Create the path for crate-devel packages
mkdir -p %{buildroot}%{_datadir}/cargo/registry

%files
%license COPYRIGHT LICENSE-APACHE LICENSE-MIT
%doc README.md
%{_bindir}/rustc
%{_bindir}/rustdoc
%{_libdir}/*.so
%{_mandir}/man1/rustc.1*
%{_mandir}/man1/rustdoc.1*
%dir %{rustlibdir}
%dir %{rustlibdir}/%{rust_triple}
%dir %{rustlibdir}/%{rust_triple}/lib
%{rustlibdir}/%{rust_triple}/lib/*.so
%{rustlibdir}/%{rust_triple}/codegen-backends/


%files std-static
%dir %{rustlibdir}
%dir %{rustlibdir}/%{rust_triple}
%dir %{rustlibdir}/%{rust_triple}/lib
%{rustlibdir}/%{rust_triple}/lib/*.rlib


%files debugger-common
%dir %{rustlibdir}
%dir %{rustlibdir}/etc
%{rustlibdir}/etc/debugger_*.py*


%files gdb
%{_bindir}/rust-gdb
%{_bindir}/rust-gdbgui
%{rustlibdir}/etc/gdb_*.py*


%files lldb
%{_bindir}/rust-lldb
%{rustlibdir}/etc/lldb_*.py*


%files -n cargo
%license src/tools/cargo/LICENSE-APACHE src/tools/cargo/LICENSE-MIT src/tools/cargo/LICENSE-THIRD-PARTY
%doc src/tools/cargo/README.md
%{_bindir}/cargo
%{_mandir}/man1/cargo*.1*
%{_sysconfdir}/bash_completion.d/cargo
%{_datadir}/zsh/site-functions/_cargo
%dir %{_datadir}/cargo
%dir %{_datadir}/cargo/registry

%changelog
* Fri Apr 12 2019 Lucien Xu <sfietkonstantin@free.fr> - 1.34.0-1
- Package 1.34.0

* Sat Mar 31 2019 Lucien Xu <sfietkonstantin@free.fr> - 1.33.0-1
- Package 1.33.0

* Sat Feb 09 2019 Lucien Xu <sfietkonstantin@free.fr> - 1.32.0-1
- Package 1.32.0

* Sat Dec 08 2018 Lucien Xu <sfietkonstantin@free.fr> - 1.31.0-1
- Package 1.31.0
- Based on Fedora packaging

