"""Directional MLB error references, independent of the KBO point estimate."""
from __future__ import annotations
import numpy as np


def reference_widths(spec, angles):
    p=np.asarray(angles,float)
    if not np.isfinite(p).all():raise ValueError('Nonfinite reference angle')
    if 'asymmetric' not in spec:
        radius=float(spec['MLB_single_period_radius_deg'])
        if not np.isfinite(radius) or radius<0:raise ValueError('Invalid MLB reference radius')
        return np.full(p.shape,radius),np.full(p.shape,radius)
    a=spec['asymmetric']
    x=np.column_stack([(p.reshape(-1)-40.)/20.,np.maximum(p.reshape(-1)-50.,0.)/20.])
    widths=[]
    for direction in ['down','up']:
        scale=a[direction+'_scale']
        predicted=x@np.asarray(scale['coefficients'],float)+float(scale['intercept'])
        multiplier=float(a[direction+'_multiplier'])
        if not np.isfinite(multiplier) or multiplier<0:raise ValueError('Invalid directional reference multiplier')
        value=multiplier*np.maximum(float(scale['minimum_scale_deg']),predicted)
        if not np.isfinite(value).all() or (value<0).any():raise ValueError('Invalid directional reference width')
        widths.append(value.reshape(p.shape))
    return tuple(widths)


def reference_envelope(spec, angles):
    p=np.asarray(angles,float)
    if p.size==0:raise ValueError('Empty reference scenarios')
    down,up=reference_widths(spec,p)
    return max(-90.,float(np.min(p-down))),min(90.,float(np.max(p+up)))
