"""Prepare public aviation support-model data without changing the raw sources."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import unicodedata
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(booking_source, profiles_source, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    if booking_source.suffix.lower() == '.zip':
        with zipfile.ZipFile(booking_source) as archive:
            names = [name for name in archive.namelist() if Path(name).name == 'customer_booking.csv']
            if len(names) != 1:
                raise ValueError('Expected exactly one customer_booking.csv in archive')
            payload = archive.read(names[0])
    else:
        payload = booking_source.read_bytes()
    booking = pd.read_csv(io.BytesIO(payload), encoding='latin1')
    if not booking.booking_complete.isin([0, 1]).all():
        raise ValueError('booking_complete must contain only binary labels')
    clean = booking.drop_duplicates().copy()
    clean.insert(0, 'source_row', clean.index.to_numpy())
    _, held = train_test_split(clean.index, test_size=.30, random_state=2026,
                               stratify=clean.booking_complete)
    val, test = train_test_split(held, test_size=.50, random_state=2026,
                                 stratify=clean.loc[held, 'booking_complete'])
    clean['split'] = 'train'
    clean.loc[val, 'split'] = 'val'
    clean.loc[test, 'split'] = 'test'

    def route_bucket(value):
        normalized = ' '.join(unicodedata.normalize('NFKC', str(value)).casefold().split())
        return int(hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:8], 16) % 100

    bucket = clean.route.map(route_bucket)
    clean['route_holdout_split'] = np.where(bucket < 70, 'train', np.where(bucket < 85, 'val', 'test'))
    clean.to_parquet(output_dir / 'booking.parquet', index=False, compression='zstd')

    profiles = pd.read_csv(profiles_source, encoding='gb18030')
    if profiles.MEMBER_NO.isna().any() or profiles.MEMBER_NO.duplicated().any():
        raise ValueError('Public profile identifiers must be complete and unique')
    # Only model inputs are retained; identifiers are never model features.
    values = profiles[['LAST_TO_END', 'FLIGHT_COUNT', 'SEG_KM_SUM', 'avg_discount']].copy()
    values['membership_days'] = (
        pd.to_datetime(profiles.LOAD_TIME, format='mixed', errors='coerce') -
        pd.to_datetime(profiles.FFP_DATE, format='mixed', errors='coerce')
    ).dt.days
    values.to_parquet(output_dir / 'profiles.parquet', index=False, compression='zstd')
    manifest = {
        'protocol': 'Public aviation support models; seed=2026; deduplicate before 70/15/15 split',
        'booking': {'raw_rows': len(booking), 'deduplicated_rows': len(clean),
                    'source_sha256': digest(booking_source),
                    'csv_sha256': hashlib.sha256(payload).hexdigest(),
                    'splits': {str(k): int(v) for k, v in clean.groupby('split').size().items()}},
        'profiles': {'raw_rows': len(profiles), 'source_sha256': digest(profiles_source)},
    }
    (output_dir / 'data-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--booking-source', type=Path, required=True)
    parser.add_argument('--profiles-source', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.booking_source, args.profiles_source, args.output_dir)
