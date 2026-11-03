'use strict';

// Minor (under-18) gate. Pure functions, no database access.
// Rule (documented in docs/minor-protection.md in the phase-4 pack):
//   - A user is minor when they declared isMinor, or when a valid
//     birthYear implies age < 18 in the current year.
//   - Declaring isMinor sticks: it can only be cleared by providing a
//     birthYear that implies adult age. Providing neither keeps the
//     existing flag (new users default to not minor).
//   - birthYear must be an integer in [1900, currentYear]; anything else
//     is ignored (never stored, never used to clear the flag).
// The gate itself lives in the ai / order / points functions: minors get
// no AI interpretation (including Pro monthly free uses), no paid
// membership purchase, and no points redemption for paid content. Free
// features (local casting, basic interpretation, knowledge, history)
// are unaffected.

function validBirthYear(value, currentYear) {
  return typeof value === 'number' && Number.isInteger(value) &&
    value >= 1900 && value <= currentYear;
}

function ageFromBirthYear(birthYear, currentYear) {
  return currentYear - birthYear;
}

function isMinorByBirthYear(birthYear, currentYear) {
  if (!validBirthYear(birthYear, currentYear)) {
    return null;
  }
  return ageFromBirthYear(birthYear, currentYear) < 18;
}

// Resolve the stored minor flag from the existing user doc and the new
// login input. Returns { minor, birthYear } where birthYear is the value
// to store (new valid input, else the existing stored value, else null).
function resolveMinor(existing, input, now) {
  const currentYear = (now || new Date()).getFullYear();
  const existingDoc = existing || {};
  const inputDoc = input || {};
  let birthYear = existingDoc.birthYear || null;
  if (validBirthYear(inputDoc.birthYear, currentYear)) {
    birthYear = inputDoc.birthYear;
  }
  if (inputDoc.isMinor === true) {
    return { minor: true, birthYear: birthYear };
  }
  if (validBirthYear(inputDoc.birthYear, currentYear)) {
    return { minor: isMinorByBirthYear(inputDoc.birthYear, currentYear), birthYear: birthYear };
  }
  return { minor: !!existingDoc.minor, birthYear: birthYear };
}

module.exports = {
  validBirthYear: validBirthYear,
  ageFromBirthYear: ageFromBirthYear,
  isMinorByBirthYear: isMinorByBirthYear,
  resolveMinor: resolveMinor
};
