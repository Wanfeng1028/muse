//! Compiled asset catalogs (`Assets.car`): the BOM store (block index, named variables, B-trees)
//! and the catalog records inside it — the CAR header, extended metadata, key format, facet
//! names, appearance names and rendition headers. Pixel data is not decoded.

use crate::FormatError;
use crate::bytes::Reader;
use serde::Serialize;
use std::collections::{BTreeMap, HashSet};

const MAX_BLOCKS: usize = 4_000_000;
const MAX_VARS: usize = 4096;
const MAX_TREE_ENTRIES: usize = 1_000_000;
const MAX_TREE_NODES: usize = 1_000_000;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Bom {
    pub version: u32,
    pub block_count: u32,
    /// (address, length) per block id.
    #[serde(skip)]
    pub blocks: Vec<(u32, u32)>,
    pub vars: Vec<(String, u32)>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CarHeader {
    pub coreui_version: u32,
    pub storage_version: u32,
    pub storage_timestamp: u32,
    pub rendition_count: u32,
    pub main_version: String,
    pub version: String,
    pub uuid: String,
    pub associated_checksum: u32,
    pub schema_version: u32,
    pub color_space_id: u32,
    pub key_semantics: u32,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Facet {
    pub name: String,
    pub attributes: BTreeMap<String, u16>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Rendition {
    /// Key attributes by name.
    pub key: BTreeMap<String, u16>,
    pub facet: Option<String>,
    pub name: Option<String>,
    pub width: Option<u32>,
    pub height: Option<u32>,
    pub scale: Option<f32>,
    pub pixel_format: Option<String>,
    pub color_space: Option<u32>,
    pub layout: Option<u16>,
    pub flags: Option<u32>,
    pub payload_bytes: Option<u32>,
    pub value_bytes: u32,
    pub csi: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct AssetCatalog {
    pub bom: Bom,
    pub header: Option<CarHeader>,
    pub extended_metadata: Option<BTreeMap<String, String>>,
    pub key_format: Vec<String>,
    pub facets: Vec<Facet>,
    pub appearances: Vec<(String, u32)>,
    pub renditions: Vec<Rendition>,
    pub warnings: Vec<String>,
}

/// Name of a rendition key attribute (best-effort names; unknown ones are `attribute-<n>`).
pub fn attribute_name(id: u32) -> String {
    match id {
        0 => "look",
        1 => "element",
        2 => "part",
        3 => "size",
        4 => "direction",
        5 => "placeholder",
        6 => "value",
        7 => "appearance",
        8 => "dimension1",
        9 => "dimension2",
        10 => "state",
        11 => "layer",
        12 => "scale",
        13 => "localization",
        14 => "presentation-state",
        15 => "idiom",
        16 => "subtype",
        17 => "identifier",
        18 => "previous-value",
        19 => "previous-state",
        20 => "horizontal-size-class",
        21 => "vertical-size-class",
        22 => "memory-level-class",
        23 => "graphics-feature-set-class",
        24 => "display-gamut",
        25 => "deployment-target",
        o => return format!("attribute-{o}"),
    }
    .into()
}

fn fourcc(v: u32) -> String {
    v.to_be_bytes().iter().map(|&b| if b.is_ascii_graphic() || b == b' ' { char::from(b) } else { '?' }).collect::<String>().trim_end().to_string()
}

fn fixed_str(b: &[u8]) -> String {
    let end = b.iter().position(|&x| x == 0).unwrap_or(b.len());
    String::from_utf8_lossy(b.get(..end).unwrap_or(b)).into_owned()
}

/// True for a BOM store.
pub fn is_bom(data: &[u8]) -> bool {
    data.starts_with(b"BOMStore")
}

/// Read the BOM container: header, block index and variables.
pub fn parse_bom(data: &[u8]) -> Result<Bom, FormatError> {
    if !is_bom(data) {
        return Err(FormatError::Malformed("no BOMStore header".into()));
    }
    let r = Reader::new(data);
    let t = || FormatError::Truncated("BOM header".into());
    let version = r.u32_be(8).ok_or_else(t)?;
    let block_count = r.u32_be(12).ok_or_else(t)?;
    let index_off = r.u32_be(16).ok_or_else(t)? as usize;
    let vars_off = r.u32_be(24).ok_or_else(t)? as usize;
    let n = r.u32_be(index_off).ok_or_else(|| FormatError::Truncated("block index".into()))? as usize;
    if n > MAX_BLOCKS || n.saturating_mul(8) > data.len() {
        return Err(FormatError::Malformed(format!("{n} blocks in a {}-byte file", data.len())));
    }
    let mut blocks = Vec::with_capacity(n);
    for i in 0..n {
        let a = r.u32_be(index_off + 4 + i * 8).ok_or_else(|| FormatError::Truncated("block index".into()))?;
        let l = r.u32_be(index_off + 8 + i * 8).ok_or_else(|| FormatError::Truncated("block index".into()))?;
        blocks.push((a, l));
    }
    let nv = r.u32_be(vars_off).ok_or_else(|| FormatError::Truncated("variables".into()))? as usize;
    let mut vars = Vec::new();
    let mut p = vars_off + 4;
    for _ in 0..nv.min(MAX_VARS) {
        let (Some(idx), Some(len)) = (r.u32_be(p), r.u8(p + 4)) else { break };
        let Some(name) = r.slice(p + 5, usize::from(len)) else { break };
        vars.push((String::from_utf8_lossy(name).into_owned(), idx));
        p += 5 + usize::from(len);
    }
    Ok(Bom { version, block_count, blocks, vars })
}

impl Bom {
    pub fn block<'a>(&self, data: &'a [u8], id: u32) -> Option<&'a [u8]> {
        let (a, l) = *self.blocks.get(id as usize)?;
        Reader::new(data).slice(a as usize, l as usize)
    }

    pub fn var<'a>(&self, data: &'a [u8], name: &str) -> Option<&'a [u8]> {
        let id = self.vars.iter().find(|(n, _)| n == name)?.1;
        self.block(data, id)
    }

    /// Entries (key bytes, value bytes) of a BOM B-tree, in order.
    pub fn tree<'a>(&self, data: &'a [u8], name: &str, warnings: &mut Vec<String>) -> Vec<(&'a [u8], &'a [u8])> {
        let mut out = Vec::new();
        let Some(t) = self.var(data, name) else { return out };
        let r = Reader::new(t);
        if t.get(..4) != Some(b"tree") {
            warnings.push(format!("{name} is not a tree"));
            return out;
        }
        let Some(mut node_id) = r.u32_be(8) else { return out };
        let mut seen = HashSet::new();
        // Descend to the leftmost leaf.
        loop {
            if !seen.insert(node_id) || seen.len() > MAX_TREE_NODES {
                warnings.push(format!("{name}: tree loops"));
                return out;
            }
            let Some(n) = self.block(data, node_id) else {
                warnings.push(format!("{name}: missing tree node {node_id}"));
                return out;
            };
            let nr = Reader::new(n);
            if nr.u16_be(0) == Some(0) {
                match nr.u32_be(12) {
                    Some(child) => node_id = child,
                    None => return out,
                }
            } else {
                break;
            }
        }
        // Walk leaves through their forward links.
        let mut leaves = HashSet::new();
        while node_id != 0 {
            if !leaves.insert(node_id) || leaves.len() > MAX_TREE_NODES {
                warnings.push(format!("{name}: leaf chain loops"));
                break;
            }
            let Some(n) = self.block(data, node_id) else {
                warnings.push(format!("{name}: missing leaf {node_id}"));
                break;
            };
            let nr = Reader::new(n);
            let count = usize::from(nr.u16_be(2).unwrap_or(0));
            for i in 0..count {
                let (Some(v), Some(k)) = (nr.u32_be(12 + i * 8), nr.u32_be(16 + i * 8)) else {
                    warnings.push(format!("{name}: leaf {node_id} cut short"));
                    break;
                };
                match (self.block(data, k), self.block(data, v)) {
                    (Some(kb), Some(vb)) => out.push((kb, vb)),
                    _ => {
                        if warnings.len() < 100 {
                            warnings.push(format!("{name}: entry points at a missing block"));
                        }
                    }
                }
                if out.len() >= MAX_TREE_ENTRIES {
                    warnings.push(format!("{name}: stopped at {MAX_TREE_ENTRIES} entries"));
                    return out;
                }
            }
            node_id = nr.u32_be(4).unwrap_or(0);
        }
        out
    }
}

/// Parse a compiled asset catalog.
pub fn parse(data: &[u8]) -> Result<AssetCatalog, FormatError> {
    let bom = parse_bom(data)?;
    let mut warnings = Vec::new();
    let header = bom.var(data, "CARHEADER").and_then(|b| {
        let r = Reader::new(b);
        Some(CarHeader {
            coreui_version: r.u32_le(4)?,
            storage_version: r.u32_le(8)?,
            storage_timestamp: r.u32_le(12)?,
            rendition_count: r.u32_le(16)?,
            main_version: fixed_str(r.slice(20, 128)?),
            version: fixed_str(r.slice(148, 256)?),
            uuid: r.slice(404, 16)?.iter().map(|x| format!("{x:02X}")).collect(),
            associated_checksum: r.u32_le(420)?,
            schema_version: r.u32_le(424)?,
            color_space_id: r.u32_le(428)?,
            key_semantics: r.u32_le(432)?,
        })
    });
    if header.is_none() {
        warnings.push("no readable CARHEADER (this BOM may not be an asset catalog)".into());
    }
    let extended_metadata = bom.var(data, "EXTENDED_METADATA").map(|b| {
        let r = Reader::new(b);
        let mut m = BTreeMap::new();
        for (i, k) in ["thinning_arguments", "deployment_platform_version", "deployment_platform", "authoring_tool"].iter().enumerate() {
            if let Some(s) = r.slice(4 + i * 256, 256) {
                m.insert((*k).to_string(), fixed_str(s));
            }
        }
        m
    });
    let key_ids: Vec<u32> = bom
        .var(data, "KEYFORMAT")
        .map(|b| {
            let r = Reader::new(b);
            let n = r.u32_le(8).unwrap_or(0) as usize;
            (0..n.min(64)).map_while(|i| r.u32_le(12 + i * 4)).collect()
        })
        .unwrap_or_default();
    let key_format: Vec<String> = key_ids.iter().map(|&i| attribute_name(i)).collect();
    let mut facets = Vec::new();
    let mut ident_to_facet: BTreeMap<u16, String> = BTreeMap::new();
    for (k, v) in bom.tree(data, "FACETKEYS", &mut warnings) {
        let name = String::from_utf8_lossy(k).trim_end_matches('\0').to_string();
        let r = Reader::new(v);
        let n = usize::from(r.u16_le(4).unwrap_or(0));
        let mut attributes = BTreeMap::new();
        for i in 0..n.min(64) {
            let (Some(a), Some(val)) = (r.u16_le(6 + i * 4), r.u16_le(8 + i * 4)) else { break };
            if a == 17 {
                ident_to_facet.insert(val, name.clone());
            }
            attributes.insert(attribute_name(u32::from(a)), val);
        }
        facets.push(Facet { name, attributes });
    }
    let appearances = bom
        .tree(data, "APPEARANCEKEYS", &mut warnings)
        .into_iter()
        .map(|(k, v)| {
            let r = Reader::new(v);
            (String::from_utf8_lossy(k).trim_end_matches('\0').to_string(), r.u32_le(0).or_else(|| r.u16_le(0).map(u32::from)).unwrap_or(0))
        })
        .collect();
    let ident_pos = key_ids.iter().position(|&i| i == 17);
    let mut renditions = Vec::new();
    for (k, v) in bom.tree(data, "RENDITIONS", &mut warnings) {
        let kr = Reader::new(k);
        let mut key = BTreeMap::new();
        for (i, id) in key_ids.iter().enumerate() {
            if let Some(val) = kr.u16_le(i * 2)
                && val != 0
            {
                key.insert(attribute_name(*id), val);
            }
        }
        let facet = ident_pos.and_then(|p| kr.u16_le(p * 2)).and_then(|id| ident_to_facet.get(&id).cloned());
        let r = Reader::new(v);
        let csi = v.get(..4) == Some(b"ISTC");
        let rd = if csi {
            Rendition {
                key,
                facet,
                name: r.slice(40, 128).map(fixed_str),
                width: r.u32_le(12),
                height: r.u32_le(16),
                scale: r.u32_le(20).map(|s| s as f32 / 100.0),
                pixel_format: r.u32_le(24).map(fourcc),
                color_space: r.u32_le(28).map(|c| c & 0xf),
                layout: r.u16_le(36),
                flags: r.u32_le(8),
                payload_bytes: r.u32_le(180),
                value_bytes: v.len() as u32,
                csi,
            }
        } else {
            Rendition {
                key,
                facet,
                name: None,
                width: None,
                height: None,
                scale: None,
                pixel_format: None,
                color_space: None,
                layout: None,
                flags: None,
                payload_bytes: None,
                value_bytes: v.len() as u32,
                csi,
            }
        };
        renditions.push(rd);
    }
    Ok(AssetCatalog { bom, header, extended_metadata, key_format, facets, appearances, renditions, warnings })
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::apple as fx;

    #[test]
    fn reads_a_catalog() {
        let c = parse(&fx::assets_car()).unwrap();
        let h = c.header.as_ref().unwrap();
        assert_eq!(h.rendition_count, 2);
        assert_eq!(h.main_version, "@(#)PROGRAM:CoreUI  PROJECT:CoreUI-1");
        assert_eq!(c.key_format, vec!["scale", "idiom", "identifier"]);
        assert_eq!(c.facets.len(), 2);
        assert_eq!(c.facets[0].name, "AppIcon");
        assert_eq!(c.renditions.len(), 2);
        let logo = c.renditions.iter().find(|r| r.facet.as_deref() == Some("Logo")).unwrap();
        assert_eq!(logo.name.as_deref(), Some("Logo@2x.png"));
        assert_eq!(logo.width, Some(64));
        assert_eq!(logo.scale, Some(2.0));
        assert_eq!(logo.pixel_format.as_deref(), Some("ARGB"));
        assert_eq!(logo.key["scale"], 2);
        assert!(c.warnings.is_empty(), "{:?}", c.warnings);
    }

    #[test]
    fn hostile_inputs() {
        let s = fx::assets_car();
        for m in craft_anything_testkit::mutations(&s) {
            let _ = parse(&m);
        }
        for i in (0..s.len()).step_by(7) {
            let _ = parse(&s[..i]);
        }
        for seed in 0..100 {
            let mut n = b"BOMStore".to_vec();
            n.extend(craft_anything_testkit::noise(seed, 256));
            let _ = parse(&n);
        }
    }
}
