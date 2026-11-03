//! Checked little/big-endian reads over untrusted bytes. Every read returns `None` when out of range.

#[derive(Debug, Clone, Copy)]
pub struct Reader<'a> {
    data: &'a [u8],
}

impl<'a> Reader<'a> {
    pub fn new(data: &'a [u8]) -> Self {
        Reader { data }
    }

    pub fn len(&self) -> usize {
        self.data.len()
    }

    pub fn is_empty(&self) -> bool {
        self.data.is_empty()
    }

    pub fn data(&self) -> &'a [u8] {
        self.data
    }

    pub fn slice(&self, off: usize, len: usize) -> Option<&'a [u8]> {
        let end = off.checked_add(len)?;
        self.data.get(off..end)
    }

    pub fn u8(&self, off: usize) -> Option<u8> {
        self.data.get(off).copied()
    }

    fn arr<const N: usize>(&self, off: usize) -> Option<[u8; N]> {
        self.slice(off, N)?.try_into().ok()
    }

    pub fn u16_le(&self, off: usize) -> Option<u16> {
        self.arr(off).map(u16::from_le_bytes)
    }

    pub fn u32_le(&self, off: usize) -> Option<u32> {
        self.arr(off).map(u32::from_le_bytes)
    }

    pub fn u64_le(&self, off: usize) -> Option<u64> {
        self.arr(off).map(u64::from_le_bytes)
    }

    pub fn u16_be(&self, off: usize) -> Option<u16> {
        self.arr(off).map(u16::from_be_bytes)
    }

    pub fn u32_be(&self, off: usize) -> Option<u32> {
        self.arr(off).map(u32::from_be_bytes)
    }

    pub fn u64_be(&self, off: usize) -> Option<u64> {
        self.arr(off).map(u64::from_be_bytes)
    }

    /// A NUL-terminated string starting at `off`, at most `max` bytes, lossily decoded.
    pub fn cstr(&self, off: usize, max: usize) -> Option<String> {
        let rest = self.data.get(off..)?;
        let rest = rest.get(..max.min(rest.len()))?;
        let end = rest.iter().position(|&b| b == 0).unwrap_or(rest.len());
        Some(String::from_utf8_lossy(rest.get(..end)?).into_owned())
    }

    /// Unsigned LEB128 at `off`: (value, bytes consumed). At most 10 bytes.
    pub fn uleb128(&self, off: usize) -> Option<(u64, usize)> {
        let mut result = 0u64;
        for i in 0..10usize {
            let b = self.u8(off.checked_add(i)?)?;
            let payload = u64::from(b & 0x7f);
            let shift = 7 * i as u32;
            if shift > 0 && payload.checked_shl(shift)? >> shift != payload {
                return None;
            }
            result |= payload << shift;
            if b & 0x80 == 0 {
                return Some((result, i + 1));
            }
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bounds_are_checked() {
        let r = Reader::new(&[1, 2, 3]);
        assert_eq!(r.u16_le(1), Some(0x0302));
        assert_eq!(r.u32_le(0), None);
        assert_eq!(r.slice(usize::MAX, 2), None);
        assert_eq!(r.cstr(0, 10).as_deref(), Some("\u{1}\u{2}\u{3}"));
        assert_eq!(Reader::new(&[0xe5, 0x8e, 0x26]).uleb128(0), Some((624485, 3)));
        assert_eq!(Reader::new(&[0x80; 12]).uleb128(0), None);
    }

    #[test]
    fn uleb128_rejects_overflow() {
        let mut v = vec![0x80; 9];
        v.push(0x7f);
        assert_eq!(Reader::new(&v).uleb128(0), None);
        let mut v = vec![0x80; 9];
        v.push(0x02);
        assert_eq!(Reader::new(&v).uleb128(0), None);
        let mut v = vec![0xff; 9];
        v.push(0x01);
        assert_eq!(Reader::new(&v).uleb128(0), Some((u64::MAX, 10)));
    }
}
