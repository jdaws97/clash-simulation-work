//! Copy-on-write plan lists. Tick callbacks keep reading the previous plan
//! snapshot while the running plan changes only the lists it actually writes.

use std::ops::{Deref, DerefMut};
use std::rc::Rc;

#[derive(Clone, Debug)]
pub struct SharedVec<T>(Rc<Vec<T>>);

impl<T> Default for SharedVec<T> {
    fn default() -> Self {
        Self(Rc::new(Vec::new()))
    }
}

impl<T> From<Vec<T>> for SharedVec<T> {
    fn from(values: Vec<T>) -> Self {
        Self(Rc::new(values))
    }
}

impl<T> FromIterator<T> for SharedVec<T> {
    fn from_iter<I: IntoIterator<Item = T>>(values: I) -> Self {
        Vec::from_iter(values).into()
    }
}

impl<T> Deref for SharedVec<T> {
    type Target = Vec<T>;

    fn deref(&self) -> &Vec<T> {
        &self.0
    }
}

impl<T: Clone> DerefMut for SharedVec<T> {
    fn deref_mut(&mut self) -> &mut Vec<T> {
        Rc::make_mut(&mut self.0)
    }
}

impl<'a, T> IntoIterator for &'a SharedVec<T> {
    type Item = &'a T;
    type IntoIter = std::slice::Iter<'a, T>;

    fn into_iter(self) -> Self::IntoIter {
        self.iter()
    }
}

impl<'a, T: Clone> IntoIterator for &'a mut SharedVec<T> {
    type Item = &'a mut T;
    type IntoIter = std::slice::IterMut<'a, T>;

    fn into_iter(self) -> Self::IntoIter {
        self.iter_mut()
    }
}
