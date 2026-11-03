"""Explicit synthetic walking profile. Values are test inputs, not health estimates."""
from decimal import Decimal, ROUND_HALF_UP

def enrich(batches, *, distance_per_step=0.7, kcal_per_step=0.04, elevation_m=0.0, workout=True):
    if not batches:return batches
    values=[Decimal(str(x)) for x in (distance_per_step,kcal_per_step,elevation_m)]
    if any(not x.is_finite() or x<0 for x in values):raise ValueError('Profile values must be finite and nonnegative')
    steps=sum(b['steps'] for b in batches)
    # Allocate by cumulative totals to avoid rounding drift in minute records.
    consumed=0;previous=[Decimal(0)]*3
    totals=[values[0]*steps,values[1]*steps,values[2]]
    for b in batches:
        consumed+=b['steps']
        current=[(v*consumed/steps).quantize(Decimal('.001'),rounding=ROUND_HALF_UP) for v in totals]
        for key,value,old in zip(('distance_m','active_kcal','elevation_m'),current,previous):b[key]=float(value-old)
        previous=current
    if workout:batches[-1]['workout_start']=batches[0]['start']
    return batches
