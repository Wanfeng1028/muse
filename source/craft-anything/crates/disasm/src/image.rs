//! An executable image: the parsed container plus its bytes, with address-level reads and
//! instruction decoding.

use crate::DisasmError;
use crate::decode::{Insn, Mode, decode};
use craft_anything_formats::{Arch, Binary, Format};
use std::sync::Arc;

#[derive(Debug, Clone)]
pub struct Image {
    pub bin: Binary,
    pub data: Arc<[u8]>,
    /// Decoding mode; `None` when the architecture isn't supported by the built-in decoder.
    pub mode: Option<Mode>,
}

pub fn mode_for(bin: &Binary) -> Option<Mode> {
    match bin.arch {
        Arch::X86_16 => Some(Mode::X16),
        Arch::X86 => Some(Mode::X32),
        Arch::X86_64 => Some(Mode::X64),
        Arch::Aarch64 => Some(Mode::A64),
        Arch::Arm => {
            if bin.entry.is_some_and(|e| e & 1 == 1) {
                Some(Mode::T32)
            } else {
                Some(Mode::A32)
            }
        }
        Arch::Other => None,
    }
}

impl Image {
    /// Parse any supported container.
    pub fn parse(data: Arc<[u8]>) -> Result<Image, DisasmError> {
        let bin = craft_anything_formats::parse_binary(&data).map_err(DisasmError::Format)?;
        Ok(Image::from_binary(data, bin))
    }

    pub fn from_binary(data: Arc<[u8]>, bin: Binary) -> Image {
        let mode = mode_for(&bin);
        Image { bin, data, mode }
    }

    /// A DOS .COM program (16-bit, loaded at 0x100).
    pub fn dos_com(data: Arc<[u8]>) -> Result<Image, DisasmError> {
        let bin = craft_anything_formats::dos::com_binary(&data).map_err(DisasmError::Format)?;
        Ok(Image::from_binary(data, bin))
    }

    /// Raw machine code for `arch`, loaded at `base`.
    pub fn raw(data: Arc<[u8]>, arch: Arch, base: u64) -> Image {
        let bin = Binary::raw(arch, base, data.len() as u64, 0);
        Image::from_binary(data, bin)
    }

    pub fn format(&self) -> Format {
        self.bin.format
    }

    /// File-backed bytes at `va` (never crossing the end of the section).
    pub fn read(&self, va: u64, len: usize) -> Option<&[u8]> {
        self.bin.read(&self.data, va, len)
    }

    pub fn is_exec(&self, va: u64) -> bool {
        self.bin.is_exec(va)
    }

    pub fn is_mapped(&self, va: u64) -> bool {
        self.bin.is_mapped(va)
    }

    /// Decode the instruction at `va`.
    pub fn decode(&self, va: u64, fmt: bool) -> Option<Insn> {
        let mode = self.mode?;
        let bytes = self.read(va, mode.max_insn_len())?;
        decode(mode, bytes, va, fmt)
    }

    pub fn pointer_size(&self) -> u64 {
        if self.bin.bits == 64 {
            8
        } else if self.bin.bits == 16 {
            2
        } else {
            4
        }
    }
}
