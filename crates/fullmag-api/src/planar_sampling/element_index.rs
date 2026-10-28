//! Bounding-volume hierarchy over element AABBs for point location (note
//! 0970 § Spatial index for point location, gate PM-N28).
//!
//! The index only narrows the candidate elements; the containment test and
//! the shape functions stay those of the direct scan. Candidates are visited
//! in ascending element index, so a point on a shared face resolves to the
//! same element as the linear traversal and the result is identical.

/// Elements per leaf; small leaves keep the containment tests per query low.
const LEAF_SIZE: usize = 8;

#[derive(Debug, Clone)]
struct BvhNode {
    min: [f64; 3],
    max: [f64; 3],
    /// Leaf: first entry in `order`; inner: index of the left child.
    start: u32,
    /// Leaf: number of elements; inner: 0 (right child follows the left subtree).
    count: u32,
    right: u32,
}

#[derive(Debug, Clone)]
pub(crate) struct ElementBvh {
    nodes: Vec<BvhNode>,
    order: Vec<u32>,
    boxes: Vec<([f64; 3], [f64; 3])>,
}

impl ElementBvh {
    /// Builds the hierarchy over `boxes[i]` for the element indices in `elements`.
    /// Boxes are padded by `padding` so points on faces stay inside them.
    pub(crate) fn build(boxes: Vec<([f64; 3], [f64; 3])>, elements: Vec<u32>, padding: f64) -> Self {
        let boxes = boxes
            .into_iter()
            .map(|(min, max)| {
                (
                    [min[0] - padding, min[1] - padding, min[2] - padding],
                    [max[0] + padding, max[1] + padding, max[2] + padding],
                )
            })
            .collect::<Vec<_>>();
        let mut index = Self { nodes: Vec::new(), order: elements, boxes };
        if !index.order.is_empty() {
            let count = index.order.len();
            index.build_node(0, count);
        }
        index
    }

    fn build_node(&mut self, start: usize, end: usize) -> u32 {
        let node_index = self.nodes.len() as u32;
        let (min, max) = self.bounds_of(start, end);
        self.nodes.push(BvhNode { min, max, start: start as u32, count: (end - start) as u32, right: 0 });
        if end - start <= LEAF_SIZE {
            return node_index;
        }
        // Median split along the longest axis of the centroid extent.
        let mut centroid_min = [f64::INFINITY; 3];
        let mut centroid_max = [f64::NEG_INFINITY; 3];
        for &element in &self.order[start..end] {
            let centroid = self.centroid(element);
            for axis in 0..3 {
                centroid_min[axis] = centroid_min[axis].min(centroid[axis]);
                centroid_max[axis] = centroid_max[axis].max(centroid[axis]);
            }
        }
        let axis = (0..3)
            .max_by(|a, b| {
                (centroid_max[*a] - centroid_min[*a]).total_cmp(&(centroid_max[*b] - centroid_min[*b]))
            })
            .unwrap_or(0);
        if !(centroid_max[axis] > centroid_min[axis]) {
            return node_index; // Coincident centroids: keep one (larger) leaf.
        }
        let middle = start + (end - start) / 2;
        let boxes = &self.boxes;
        let centroid = |element: u32| {
            let (min, max) = boxes[element as usize];
            0.5 * (min[axis] + max[axis])
        };
        self.order[start..end].select_nth_unstable_by(middle - start, |left, right| {
            centroid(*left).total_cmp(&centroid(*right)).then(left.cmp(right))
        });
        self.nodes[node_index as usize].count = 0;
        let left = self.build_node(start, middle);
        let right = self.build_node(middle, end);
        let node = &mut self.nodes[node_index as usize];
        node.start = left;
        node.right = right;
        node_index
    }

    fn centroid(&self, element: u32) -> [f64; 3] {
        let (min, max) = self.boxes[element as usize];
        [0.5 * (min[0] + max[0]), 0.5 * (min[1] + max[1]), 0.5 * (min[2] + max[2])]
    }

    fn bounds_of(&self, start: usize, end: usize) -> ([f64; 3], [f64; 3]) {
        let mut min = [f64::INFINITY; 3];
        let mut max = [f64::NEG_INFINITY; 3];
        for &element in &self.order[start..end] {
            let (element_min, element_max) = self.boxes[element as usize];
            for axis in 0..3 {
                min[axis] = min[axis].min(element_min[axis]);
                max[axis] = max[axis].max(element_max[axis]);
            }
        }
        (min, max)
    }

    /// Element indices whose padded box contains `point`, ascending.
    pub(crate) fn candidates(&self, point: [f64; 3], out: &mut Vec<u32>) {
        out.clear();
        if self.nodes.is_empty() {
            return;
        }
        let contains = |min: &[f64; 3], max: &[f64; 3]| {
            (0..3).all(|axis| point[axis] >= min[axis] && point[axis] <= max[axis])
        };
        let mut stack = vec![0u32];
        while let Some(node_index) = stack.pop() {
            let node = &self.nodes[node_index as usize];
            if !contains(&node.min, &node.max) {
                continue;
            }
            if node.count > 0 {
                for &element in &self.order[node.start as usize..(node.start + node.count) as usize] {
                    let (min, max) = &self.boxes[element as usize];
                    if contains(min, max) {
                        out.push(element);
                    }
                }
            } else {
                stack.push(node.right);
                stack.push(node.start);
            }
        }
        out.sort_unstable();
    }
}

#[cfg(test)]
mod tests {
    use super::ElementBvh;

    fn unit_boxes(count: usize) -> Vec<([f64; 3], [f64; 3])> {
        // A row of unit cubes along x, shuffled by a fixed stride.
        (0..count)
            .map(|index| {
                let x = ((index * 7) % count) as f64;
                ([x, 0.0, 0.0], [x + 1.0, 1.0, 1.0])
            })
            .collect()
    }

    #[test]
    fn candidates_equal_the_linear_box_scan() {
        let boxes = unit_boxes(97);
        let index = ElementBvh::build(boxes.clone(), (0..97).collect(), 0.0);
        let mut found = Vec::new();
        for step in 0..400 {
            let point = [step as f64 * 0.2437, 0.5, 0.5];
            index.candidates(point, &mut found);
            let expected = (0..97u32)
                .filter(|element| {
                    let (min, max) = boxes[*element as usize];
                    (0..3).all(|axis| point[axis] >= min[axis] && point[axis] <= max[axis])
                })
                .collect::<Vec<_>>();
            assert_eq!(found, expected, "point {point:?}");
        }
    }

    /// Structured cube of `n`³ cells, six Tet4 each, with every third element unselected.
    fn tet_cube(n: usize) -> crate::planar_sampling::FemPlanarField {
        let index = |i: usize, j: usize, k: usize| (i + (n + 1) * (j + (n + 1) * k)) as u32;
        let mut nodes = Vec::new();
        for k in 0..=n {
            for j in 0..=n {
                for i in 0..=n {
                    nodes.push([i as f64 * 1e-9, j as f64 * 1e-9, k as f64 * 1e-9]);
                }
            }
        }
        let mut elements = Vec::new();
        for k in 0..n {
            for j in 0..n {
                for i in 0..n {
                    let c = [
                        index(i, j, k), index(i + 1, j, k), index(i + 1, j + 1, k), index(i, j + 1, k),
                        index(i, j, k + 1), index(i + 1, j, k + 1), index(i + 1, j + 1, k + 1), index(i, j + 1, k + 1),
                    ];
                    for tet in [[0, 1, 2, 6], [0, 2, 3, 6], [0, 3, 7, 6], [0, 7, 4, 6], [0, 4, 5, 6], [0, 5, 1, 6]] {
                        elements.push([c[tet[0]], c[tet[1]], c[tet[2]], c[tet[3]]]);
                    }
                }
            }
        }
        let markers = (0..elements.len()).map(|element| u32::from(element % 3 != 2)).collect();
        let values = nodes.iter().map(|p| 2.0e9 * p[0] - 3.0e9 * p[1] + 5.0e9 * p[2] + 7.0).collect();
        crate::planar_sampling::FemPlanarField::new(1, nodes, elements, markers, values).unwrap()
    }

    #[test]
    fn indexed_fem_location_equals_the_direct_scan() {
        let n = 6;
        let field = tet_cube(n);
        let index = crate::planar_sampling::fem::element_index(&field);
        let mut candidates = Vec::new();
        let mut state = 0x2545_f491_4f6c_dd1du64;
        let mut next = || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 11) as f64 / (1u64 << 53) as f64
        };
        for sample in 0..2_000 {
            // Interior points, points on cell faces/edges and points just outside.
            let mut point = [next() * n as f64, next() * n as f64, next() * n as f64];
            if sample % 4 == 0 {
                point[sample % 3] = (point[sample % 3]).round();
            }
            if sample % 50 == 0 {
                point[0] = n as f64 + 0.25;
            }
            let point = point.map(|value| value * 1e-9);
            let direct = crate::planar_sampling::fem::interpolate_at(&field, point);
            let indexed = crate::planar_sampling::fem::interpolate_at_indexed(&field, &index, &mut candidates, point);
            assert_eq!(direct, indexed, "point {point:?}");
            assert!(candidates.len() <= 48, "candidate count {} at {point:?}", candidates.len());
        }
    }

    #[test]
    fn skipped_elements_and_far_points_have_no_candidates() {
        let boxes = unit_boxes(16);
        let index = ElementBvh::build(boxes, (0..16).filter(|element| element % 2 == 0).collect(), 0.0);
        let mut found = Vec::new();
        index.candidates([100.0, 0.5, 0.5], &mut found);
        assert!(found.is_empty());
        for x in 0..16 {
            index.candidates([x as f64 + 0.5, 0.5, 0.5], &mut found);
            assert!(found.iter().all(|element| element % 2 == 0));
        }
    }
}
