import test from 'node:test';
import assert from 'node:assert/strict';
import {formatMetricValue} from '../src/metric-format.js';

test('EC values are displayed without floating-point tails', () => {
  assert.equal(formatMetricValue('ec', 1.2000000000000002), '1.2');
  assert.equal(formatMetricValue('ec', 1.23456), '1.235');
  assert.equal(formatMetricValue('ec', 0), '0');
  assert.equal(formatMetricValue('ec', null), '—');
});

test('formatting EC does not change other metric displays', () => {
  assert.equal(formatMetricValue('ph', 6.300000000000001), 6.300000000000001);
});
