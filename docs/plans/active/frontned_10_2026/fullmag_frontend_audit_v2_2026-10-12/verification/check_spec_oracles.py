#!/usr/bin/env python3
"""Check independent document fixtures. Does not import or test Fullmag code."""
from pathlib import Path
import itertools, json, math, re, sys
ROOT = Path(__file__).resolve().parents[1]
checks = []
def check(name, passed, details=None):
    checks.append({'name': name, 'passed': bool(passed), 'details': details})
def close(a,b,tol): return abs(a-b) <= tol
def matvec(A,v): return [sum(a*b for a,b in zip(row,v)) for row in A]
def add(a,b): return [x+y for x,y in zip(a,b)]
def sub(a,b): return [x-y for x,y in zip(a,b)]
def values_close(a,b,tol): return len(a)==len(b) and all(close(x,y,tol) for x,y in zip(a,b))
def main():
    f=json.loads((ROOT/'fixtures/transform_oracles.json').read_text(encoding='utf-8'))
    q=f['quaternion_xyzw'];n=math.sqrt(sum(v*v for v in q));x,y,z,w=[v/n for v in q]
    R=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
       [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
       [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]
    A=[[v*f['scale'][j] for j,v in enumerate(row)] for row in R]
    p=f['pivot'];t=f['translation'];b=add(t,sub(p,matvec(A,p)))
    tol=f['tolerance']['point_abs_m']
    check('TRS linear and affine matrix', all(values_close(a,b_,1e-14) for a,b_ in zip(A,f['expected_linear'])) and values_close(b,f['expected_offset'],tol), {'computed_offset_m':b})
    transform=lambda v:add(matvec(A,v),b)
    check('TRS control points',all(values_close(transform(v['local']),v['world'],tol) for v in f['control_points']))
    corners=list(itertools.product(*zip(f['local_bounds']['min'],f['local_bounds']['max'])))
    world=[transform(c) for c in corners]
    wmin=[min(v[i] for v in world) for i in range(3)];wmax=[max(v[i] for v in world) for i in range(3)]
    check('TRS AABB of box corners',values_close(wmin,f['expected_world_bounds']['min'],tol) and values_close(wmax,f['expected_world_bounds']['max'],tol),{'computed_min_m':wmin,'computed_max_m':wmax})
    newp=f['pivot_only']['new_pivot'];delta=sub(p,newp);newt=add(t,sub(delta,matvec(A,delta)));newb=add(newt,sub(newp,matvec(A,newp)))
    check('Pivot-only invariant',values_close(newt,f['pivot_only']['expected_new_translation'],tol) and values_close(newb,b,tol))
    c=math.sqrt(.5);col1=[2*c,c,0];col2=[-2*c,c,0];dot=sum(a*b for a,b in zip(col1,col2))
    check('Future hierarchy shear counterexample',close(dot,-1.5,1e-14),{'column_dot':dot,'production_status':'unsupported in proposed R1/R2'})
    f=json.loads((ROOT/'fixtures/slice_oracle.json').read_text(encoding='utf-8'));verts=f['vertices'];n=f['plane']['normal'];off=f['plane']['offset_m'];pts=[]
    for i,j in itertools.combinations(range(4),2):
        a,c=verts[i],verts[j];da=sum(x*y for x,y in zip(n,a))-off;dc=sum(x*y for x,y in zip(n,c))-off
        if da*dc<0:
            lam=da/(da-dc);pts.append([a[k]+lam*(c[k]-a[k]) for k in range(3)])
    check('Tetra plane intersection',len(pts)==3 and all(any(values_close(p,e,1e-20) for p in pts) for e in f['expected_polygon_unordered']), {'computed_vertices_m':pts})
    u=sub(pts[1],pts[0]);v=sub(pts[2],pts[0]);cross=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]];area=.5*math.sqrt(sum(x*x for x in cross))
    check('Tetra intersection area',close(area,f['expected_area_m2'],f['tolerance']['area_abs_m2']),{'computed_area_m2':area})
    nf=json.loads((ROOT/'fixtures/numeric_oracles.json').read_text(encoding='utf-8'));units={'m':1,'mm':1e-3,'um':1e-6,'µm':1e-6,'μm':1e-6,'nm':1e-9}
    pattern=re.compile(r'^([+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?)(?: ?(nm|um|µm|μm|mm|m))?$')
    def parse(raw):
        s=raw.strip()
        if not s:return 'empty',None
        if s in nf['incomplete']:return 'incomplete',None
        m=pattern.fullmatch(s)
        if not m:return 'invalid',None
        value=float(m[1].replace(',','.'))*units[m[2] or nf['default_unit']]
        return ('valid',value) if math.isfinite(value) else ('invalid',None)
    good=all(parse(c['raw'])[0]=='valid' and close(parse(c['raw'])[1],c['expected_si'],1e-20) for c in nf['valid'])
    good=good and all(parse(s)[0]==category for category in ['empty','incomplete','invalid'] for s in nf[category])
    check('Numeric grammar fixture reference only',good)
    no=nf['no_op'];eps=no['ulp_multiplier']*math.ulp(max(abs(no['a_m']),abs(no['b_m']),no['Lchar_m']))
    check('1pm is not a no-op at 100nm characteristic size',abs(no['a_m']-no['b_m'])>eps,{'epsilon_m':eps})
    quant=lambda a:math.copysign(math.floor(abs(a)+.5),a)
    check('Symmetric snap half ties', [quant(a) for a in [.5,-.5,1.5,-1.5]]==[1,-1,2,-2])
    report={'scope':'independent specification algebra; not production tests','status':'pass' if all(x['passed'] for x in checks) else 'failed','checks':checks,'fullmag_executed':False}
    print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if report['status']=='pass' else 1
if __name__=='__main__':sys.exit(main())
