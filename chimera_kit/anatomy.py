"""Independent, parameter-driven anatomy. Coordinates: Z up, -Y forward."""
from dataclasses import dataclass, field
from math import sin, pi

@dataclass
class Blueprint:
    species: str
    size: float
    bones: list = field(default_factory=list)
    forms: list = field(default_factory=list)
    limbs: list = field(default_factory=list)

    def bone(self, name, head, tail, parent=None, deform=True, radius=0, group="Body", box=None):
        """box=(width0, depth0, width1, depth1): cross-section at head and tail
        for the box mannequin. Width runs side to side, depth front to back."""
        self.bones.append(dict(name=name, head=head, tail=tail, parent=parent,
                               deform=deform, radius=radius, group=group, box=box))
        return name

    def form(self, bone, center, scale, color=0, ball=None):
        """ball: a named material for a round form drawn in every mannequin style."""
        self.forms.append(dict(bone=bone, center=center, scale=scale, color=color, ball=ball))

FINGERS=("thumb","index","middle","ring","pinky")

def girth(p,u):
    """Trunk thickness along the body: hips at u=0, belly near the middle, chest at u=1."""
    hips,belly,chest=p.hip_size,p.belly_size,p.chest_size
    if u<.45:
        t=u/.45
        return hips+(belly-hips)*t*t*(3-2*t)
    t=(u-.45)/.55
    return belly+(chest-belly)*t*t*(3-2*t)

def neck_chain(b,points,links,parent,size0,size1):
    """Neck bones along a polyline: "neck", "neck.02", ... Returns the last name.
    size0/size1: box side at the base and at the top."""
    lengths=[sum((points[i+1][j]-points[i][j])**2 for j in range(3))**.5 for i in range(len(points)-1)]
    total=sum(lengths) or 1e-6
    def at(t):
        distance=t*total
        for i,length in enumerate(lengths):
            if distance<=length or i==len(lengths)-1:
                f=distance/max(length,1e-9)
                return tuple(points[i][j]+(points[i+1][j]-points[i][j])*f for j in range(3))
            distance-=length
    for k in range(links):
        name="neck" if k==0 else f"neck.{k+1:02d}"
        s0=size0+(size1-size0)*k/links
        s1=size0+(size1-size0)*(k+1)/links
        parent=b.bone(name,at(k/links),at((k+1)/links),parent,box=(s0,s0*1.1,s1,s1*1.1),radius=s0*.5)
    return parent

def biped(p):
    """Box-figure biped: centre of mass, pelvis, spine, clavicles, arms with
    fingers, legs with a separate toe. Arms hang relaxed at the sides."""
    h=p.size
    b=Blueprint("BIPED",h)
    wide=p.body_width
    leg=p.leg_length
    ankle_z=h*.045
    knee_z=ankle_z+h*.24*leg
    hip_z=knee_z+h*.245*leg
    zp=hip_z+h*.025
    b.bone("CTRL-root",(0,0,0),(0,0,h*.12),deform=False,group="Controls")
    b.bone("CTRL-body",(0,0,zp),(0,0,zp+h*.12),"CTRL-root",False,group="Controls")
    top=zp+h*.045
    b.bone("pelvis",(0,0,zp),(0,0,top),"CTRL-body",
           box=(h*.17*wide*p.hip_size,h*.095*p.hip_size,h*.15*wide*p.hip_size,h*.09*p.hip_size),radius=h*.06*p.hip_size)
    torso=h*.225*p.body_length
    spine=[]
    n=p.spine_links
    for i in range(n):
        u0,u1=i/n,(i+1)/n
        name=f"spine.{i+1:02d}"
        g0,g1=girth(p,u0),girth(p,u1)
        w0=h*(.145+.055*u0)*wide*g0
        w1=h*(.145+.055*u1)*wide*g1
        b.bone(name,(0,0,top+torso*u0),(0,0,top+torso*u1),spine[-1] if spine else "pelvis",
               box=(w0,h*(.085+.02*u0)*g0,w1,h*(.085+.02*u1)*g1),radius=h*.07*g0)
        spine.append(name)
    chest=top+torso
    neck_top=chest+h*.055*p.neck_length
    neck=neck_chain(b,[(0,0,chest),(0,0,neck_top)],p.neck_links,spine[-1],h*.05,h*.045)
    hs=p.head_size
    b.bone("head",(0,0,neck_top),(0,0,neck_top+h*.125*hs),neck,
           box=(h*.082*hs,h*.098*hs,h*.09*hs,h*.105*hs),radius=h*.05)
    for side,sign in (("L",1),("R",-1)):
        # Legs
        prefix=f"leg.01.{side}"
        x=sign*h*.052*wide
        hip=(x,0,hip_z)
        knee=(x*1.04,-h*.014,knee_z)
        ankle=(x*1.08,h*.012,ankle_z)
        ball=(ankle[0],ankle[1]-h*.09,h*.014)
        tip=(ankle[0],ball[1]-h*.05,h*.014)
        upper,lower,foot=prefix+".upper",prefix+".lower",prefix+".foot"
        b.bone(upper,hip,knee,"pelvis",group="Legs",box=(h*.078,h*.082,h*.058,h*.062),radius=h*.038)
        b.bone(lower,knee,ankle,upper,group="Legs",box=(h*.058,h*.062,h*.04,h*.044),radius=h*.028)
        b.bone(foot,ankle,ball,lower,group="Legs",box=(h*.05,h*.05,h*.056,h*.026),radius=h*.025)
        b.bone(f"toe.{side}",ball,tip,foot,group="Legs",box=(h*.056,h*.024,h*.05,h*.018),radius=h*.015)
        control="CTRL-"+prefix
        b.bone(control,ankle,ball,"CTRL-root",False,group="Feet IK")
        pole=(knee[0],knee[1]-h*.25,knee[2])
        pole_name="POLE-"+prefix
        b.bone(pole_name,pole,(pole[0],pole[1],pole[2]+h*.05),"CTRL-root",False,group="Poles")
        b.limbs.append(dict(upper=upper,lower=lower,foot=foot,control=control,pole=pole_name,
            ankle=ankle,knee=knee,index=0,side=sign,
            reach=sum((hip[j]-ankle[j])**2 for j in range(3))**.5))
        # Arms
        shoulder_z=chest-h*.012
        inner=(sign*h*.018,0,shoulder_z)
        sh=(sign*h*.105*wide,0,shoulder_z)
        b.bone(f"clavicle.{side}",inner,sh,spine[-1],group="Arms",box=(h*.046,h*.036,h*.042,h*.034),radius=h*.02)
        al=p.arm_length
        out=(sign*.16,0,-.987)
        def along(point,distance):
            return tuple(point[j]+out[j]*distance for j in range(3))
        elbow=along(sh,h*.16*al)
        elbow=(elbow[0],h*.006,elbow[2])
        wrist=along(elbow,h*.145*al)
        wrist=(wrist[0],-h*.004,wrist[2])
        knuckle=along(wrist,h*.05)
        b.bone(f"arm.{side}",sh,elbow,f"clavicle.{side}",group="Arms",box=(h*.05,h*.054,h*.042,h*.046),radius=h*.027)
        b.bone(f"forearm.{side}",elbow,wrist,f"arm.{side}",group="Arms",box=(h*.042,h*.046,h*.032,h*.038),radius=h*.022)
        b.bone(f"hand.{side}",wrist,knuckle,f"forearm.{side}",group="Arms",box=(h*.02,h*.046,h*.02,h*.052),radius=h*.02)
        count=max(0,min(5,p.fingers))
        links=max(1,min(3,p.finger_links))
        for f in range(count):
            name=FINGERS[f]
            if name=="thumb":
                start=(wrist[0]+out[0]*h*.015,wrist[1]-h*.024,wrist[2]+out[2]*h*.015)
                direction=(out[0]*.6,-.62,out[2]*.6)
                length=h*.045
            else:
                spread=(f-2.5)/1.5
                start=(knuckle[0],knuckle[1]+spread*h*.018,knuckle[2])
                direction=(out[0],spread*.07,out[2])
                length=h*(.05 if name in {"index","ring"} else .056 if name=="middle" else .04)
            parent=f"hand.{side}"
            for k in range(links):
                a=tuple(start[j]+direction[j]*length*k/links for j in range(3))
                c=tuple(start[j]+direction[j]*length*(k+1)/links for j in range(3))
                parent=b.bone(f"{name}.{k+1:02d}.{side}",a,c,parent,group="Fingers",
                    box=(h*.011,h*.011,h*.009,h*.009),radius=h*.006)
    return b

THEROPODS={
    # hip: leg height; body: trunk length; girth: trunk thickness; neck: neck length;
    # head: skull size; snout: skull length; tail: tail length; arms: arm size (0 = none)
    "ALLOSAUR":dict(hip=1.0,body=1.0,girth=1.0,neck=1.0,head=1.0,snout=1.0,tail=1.0,arms=1.55,claws=3),
    "TREX":dict(hip=1.0,body=1.0,girth=1.15,neck=.78,head=1.3,snout=1.0,tail=1.0,arms=.6,claws=2),
    "BIRD":dict(hip=.55,body=.62,girth=.85,neck=.55,head=.62,snout=.55,tail=.30,arms=0,beak=True,fan=True),
    "EAGLE":dict(hip=.62,body=.72,girth=.95,neck=.6,head=.68,snout=.6,tail=.40,arms=0,beak=True,fan=True),
    "OSTRICH":dict(hip=1.45,body=.85,girth=1.05,neck=2.3,head=.5,snout=.6,tail=.22,arms=0,beak=True,fan=True),
    "MECH_POD":dict(hip=1.05,body=.25,girth=1.0,neck=.2,head=1.9,snout=.75,tail=0,arms=1.0,pod=True),
}

def theropod(p):
    """Two-legged, level-bodied walkers: dinosaurs, birds and the walker pod.
    Level spine over the hips, tail as counterweight, S-curved neck and
    digitigrade legs. THEROPODS holds the proportions that tell them apart."""
    h=p.size
    style=THEROPODS[p.species]
    pod=style.get("pod",False)
    beak=style.get("beak",False)
    b=Blueprint(p.species,h)
    wide=p.body_width*style["girth"]
    deep=style["girth"]
    leg=p.leg_length*style["hip"]
    z=h*.56*leg
    length=h*.42*p.body_length*style["body"]
    b.bone("CTRL-root",(0,0,0),(0,0,h*.12),deform=False,group="Controls")
    b.bone("CTRL-body",(0,0,z),(0,0,z+h*.12),"CTRL-root",False,group="Controls")
    # The hips lie along the body and are its widest part: the legs hang from them.
    hips=p.hip_size
    rear=h*.13
    b.bone("pelvis",(0,rear,z+h*.02),(0,-h*.03,z+h*.03),"CTRL-body",
           box=(h*.20*wide*hips,h*.23*deep*hips,h*.215*wide*hips,h*.25*deep*hips),radius=h*.10*deep*hips)
    spine=[]
    n=p.spine_links
    for i in range(n):
        u0,u1=i/n,(i+1)/n
        name=f"spine.{i+1:02d}"
        b.bone(name,(0,-h*.03-length*u0,z+h*.03+h*.04*u0),(0,-h*.03-length*u1,z+h*.03+h*.04*u1),
               spine[-1] if spine else "pelvis",
               box=(h*(.18-.03*u0)*wide*girth(p,u0),h*(.21-.04*u0)*deep*girth(p,u0),
                    h*(.18-.03*u1)*wide*girth(p,u1),h*(.21-.04*u1)*deep*girth(p,u1)),radius=h*.085*deep*girth(p,u0))
        spine.append(name)
    chest=(0,-h*.03-length,z+h*.07)
    nk=style["neck"]*p.neck_length
    neck_mid=(0,chest[1]-h*.10*min(nk,1.2),chest[2]+h*.13*nk)
    neck_top=(0,chest[1]-h*.15*min(nk,1.2),chest[2]+h*.27*nk)
    hs=p.head_size*style["head"]
    thick=.6 if beak else 1.0
    snout=(0,neck_top[1]-h*.27*hs*style["snout"],neck_top[2]-h*(.035 if not pod else 0))
    # One neck link means the two-bone S-curve; more links subdivide it.
    neck=neck_chain(b,[chest,neck_mid,neck_top],p.neck_links+1,spine[-1],h*.11*thick,h*.08*thick)
    if pod:
        # The cockpit: a blunt block rather than a tapering skull.
        b.bone("head",neck_top,snout,neck,box=(h*.16*hs,h*.15*hs,h*.14*hs,h*.12*hs),radius=h*.07*hs)
    elif beak:
        b.bone("head",neck_top,snout,neck,box=(h*.105*hs,h*.115*hs,h*.03*hs,h*.03*hs),radius=h*.045*hs)
    else:
        b.bone("head",neck_top,snout,neck,box=(h*.105*hs,h*.115*hs,h*.06*hs,h*.065*hs),radius=h*.05*hs)
        jaw_root=(0,neck_top[1]-h*.02,neck_top[2]-h*.065*hs)
        if p.jaw: b.bone("jaw",jaw_root,(0,snout[1]+h*.02,snout[2]-h*.05*hs),"head",
               box=(h*.085*hs,h*.035*hs,h*.05*hs,h*.022*hs),radius=h*.02*hs,group="Details")
    parent="pelvis"
    tail_length=h*style["tail"]*p.tail_length
    links=max(1,p.tail_links)
    for i in range(p.tail_links if tail_length else 0):
        u0,u1=i/links,(i+1)/links
        name=f"tail.{i+1:02d}"
        if style.get("fan"):
            # Tail feathers: flat and widening.
            box=(h*(.10+.10*u0),h*.03,h*(.10+.10*u1),h*.02)
        else:
            base=deep*hips
            box=(h*.15*(1-.9*u0)*base,h*.17*(1-.9*u0)*base,h*.15*(1-.9*u1)*base,h*.17*(1-.9*u1)*base)
        b.bone(name,(0,rear+tail_length*u0,z+h*.03-h*.10*u0*style["tail"]),
               (0,rear+tail_length*u1,z+h*.03-h*.10*u1*style["tail"]),parent,
               box=box,radius=h*.075*(1-u0*.86),group="Tail")
        parent=name
    pairs=p.leg_pairs
    for i in range(pairs):
        y0=-length*i/max(1,pairs-1) if pairs>1 else 0
        for side,sign in (("L",1),("R",-1)):
            prefix=f"leg.{i+1:02d}.{side}"
            x=sign*h*.085*wide
            hip=(x,y0,z)
            knee=(x*1.05,y0-h*.13*min(leg,1.2),z-h*.24*leg)
            ankle=(x*1.05,y0+h*.07*min(leg,1.2),h*.17*leg)
            ball=(ankle[0],y0-h*.03,h*.025)
            tip=(ankle[0],y0-h*.19*(1.0 if not beak else .7),h*.02)
            upper,lower,foot=prefix+".upper",prefix+".lower",prefix+".foot"
            slim=.6 if beak else 1.0
            b.bone(upper,hip,knee,"pelvis" if i==0 else spine[-1],group="Legs",
                   box=(h*.085*deep,h*.13*deep,h*.06*slim,h*.08*slim),radius=h*.05*slim)
            b.bone(lower,knee,ankle,upper,group="Legs",box=(h*.055*slim,h*.075*slim,h*.038*slim,h*.045*slim),radius=h*.032*slim)
            b.bone(foot,ankle,ball,lower,group="Legs",box=(h*.04*slim,h*.045*slim,h*.05*slim,h*.04*slim),radius=h*.024*slim)
            b.bone(f"toe.{i+1:02d}.{side}",ball,tip,foot,group="Legs",box=(h*.07,h*.035,h*.045,h*.02),radius=h*.02)
            control="CTRL-"+prefix
            b.bone(control,ankle,ball,"CTRL-root",False,group="Feet IK")
            pole=(knee[0],knee[1]-h*.30,knee[2])
            pole_name="POLE-"+prefix
            b.bone(pole_name,pole,(pole[0],pole[1],pole[2]+h*.05),"CTRL-root",False,group="Poles")
            b.limbs.append(dict(upper=upper,lower=lower,foot=foot,control=control,pole=pole_name,
                ankle=ankle,knee=knee,index=i,side=sign,
                reach=sum((hip[j]-ankle[j])**2 for j in range(3))**.5))
    al=p.arm_length*style["arms"]
    for side,sign in (("L",1),("R",-1)) if al else ():
        if pod:
            # Side guns: straight barrels slung beside the cockpit.
            x=sign*h*.12*hs
            sh=(x,neck_top[1]+h*.02,neck_top[2]-h*.04)
            elbow=(x,sh[1]-h*.10*al,sh[2])
            wrist=(x,elbow[1]-h*.14*al,sh[2])
            b.bone("arm."+side,sh,elbow,"head",group="Arms",box=(h*.06,h*.06,h*.05,h*.05),radius=h*.03)
            b.bone("forearm."+side,elbow,wrist,"arm."+side,group="Arms",box=(h*.035,h*.035,h*.03,h*.03),radius=h*.017)
            continue
        x=sign*h*.075*wide
        sh=(x,chest[1]+h*.03,chest[2]-h*.09)
        elbow=(x,sh[1]+h*.035*al,sh[2]-h*.085*al)
        wrist=(x,elbow[1]-h*.075*al,elbow[2]-h*.045*al)
        claw=(x,wrist[1]-h*.035*al,wrist[2]-h*.04*al)
        b.bone("arm."+side,sh,elbow,spine[-1],group="Arms",box=(h*.035,h*.04,h*.03,h*.032),radius=h*.02)
        b.bone("forearm."+side,elbow,wrist,"arm."+side,group="Arms",box=(h*.03,h*.032,h*.024,h*.026),radius=h*.016)
        b.bone("hand."+side,wrist,claw,"forearm."+side,group="Arms",box=(h*.03,h*.02,h*.012,h*.01),radius=h*.012)
        count=style.get("claws",3)
        for k in range(count):
            spread=(k-(count-1)/2)*h*.012
            b.bone(f"claw.{k+1}.{side}",claw,(x+spread,claw[1]-h*.03*al,claw[2]-h*.025*al),"hand."+side,
                   group="Arms",box=(h*.008,h*.008,h*.003,h*.003),radius=h*.004)
    return b

SWIMMERS={
    # w/d: body width and depth; front: head-to-middle length; head: head length; tail: tail length;
    # dorsal: dorsal fin height; fluke: flat horizontal tail fin (cetaceans) instead of an upright one
    "FISH":dict(w=.09,d=.26,front=.30,head=.16,tail=.34,dorsal=.10,fin=.12,caudal=.26,fluke=False,snout=.5),
    "SHARK":dict(w=.14,d=.19,front=.50,head=.26,tail=.55,dorsal=.20,fin=.24,caudal=.34,fluke=False,snout=.25),
    "DOLPHIN":dict(w=.16,d=.18,front=.42,head=.16,tail=.50,dorsal=.13,fin=.17,caudal=.34,fluke=True,snout=.6,beak=.16),
    "WHALE":dict(w=.30,d=.30,front=.55,head=.42,tail=.70,dorsal=.05,fin=.30,caudal=.60,fluke=True,snout=.9),
    # ground: lies on the floor instead of floating; even: one thickness along the whole body
    "TADPOLE":dict(w=.26,d=.24,front=.16,head=.16,tail=.75,dorsal=0,fin=0,caudal=.16,fluke=False,snout=.75,thin_tail=.22),
    "SNAKE":dict(w=.055,d=.05,front=.95,head=.10,tail=1.25,dorsal=0,fin=0,caudal=0,fluke=False,snout=.7,ground=True,even=True),
    "WORM":dict(w=.07,d=.065,front=.38,head=.06,tail=.40,dorsal=0,fin=0,caudal=0,fluke=False,snout=.9,ground=True,even=True),
}

def swimmer(p):
    """Legless swimmers: a spine running forward from the middle of the body,
    a tail running back to a tail fin, a dorsal fin and two pectoral fins."""
    h=p.size
    style=SWIMMERS[p.species]
    b=Blueprint(p.species,h)
    w=h*style["w"]*p.body_width
    d=h*style["d"]
    # A crawler rests its belly on the floor: its centre sits half the deepest box above it.
    z=d*.58 if style.get("ground") else h*.6
    even=style.get("even",False)
    b.bone("CTRL-root",(0,0,0),(0,0,h*.12),deform=False,group="Controls")
    b.bone("CTRL-body",(0,0,z),(0,0,z+h*.12),"CTRL-root",False,group="Controls")
    b.bone("pelvis",(0,h*.02,z),(0,-h*.02,z),"CTRL-body",box=(w,d,w,d),radius=d*.4)
    front=h*style["front"]*p.body_length
    spine=[]
    n=p.spine_links
    for i in range(n):
        u0,u1=i/n,(i+1)/n
        name=f"spine.{i+1:02d}"
        # Fullest a third of the way forward, narrowing to the head.
        f0,f1=(1,1) if even else (1-.35*u0*u0,1-.35*u1*u1)
        b.bone(name,(0,-h*.02-front*u0,z),(0,-h*.02-front*u1,z),spine[-1] if spine else "pelvis",
               box=(w*f0,d*f0,w*f1,d*f1),radius=d*.4*f0)
        spine.append(name)
    nose=-h*.02-front
    hl=h*style["head"]*p.head_size
    b.bone("head",(0,nose,z),(0,nose-hl,z-h*.01),spine[-1],
           box=(w*(1.25 if even else .65),d*(1.1 if even else .65),w*style["snout"]*(1.1 if even else .5),
                d*style["snout"]*(.8 if even else .5)),radius=d*(.5 if even else .26))
    if style.get("beak"):
        b.bone("beak",(0,nose-hl,z-h*.012),(0,nose-hl-h*style["beak"],z-h*.02),"head",
               box=(w*.22,d*.16,w*.12,d*.08),radius=d*.06,group="Details")
    tail_length=h*style["tail"]*p.tail_length
    links=max(1,p.tail_links)
    parent="pelvis"
    for i in range(links):
        u0,u1=i/links,(i+1)/links
        name=f"tail.{i+1:02d}"
        f0,f1=1-.82*u0,1-.82*u1
        if even:
            # Full thickness for most of its length, tapering only near the tip.
            f0,f1=min(1,(1-u0)*2.2),min(1,(1-u1)*2.2)
        thin=style.get("thin_tail")
        if thin:
            f0,f1=thin*(1-.7*u0),thin*(1-.7*u1)
        b.bone(name,(0,h*.02+tail_length*u0,z),(0,h*.02+tail_length*u1,z),parent,
               box=(w*f0,d*f0,w*f1,d*f1),radius=d*.4*f0,group="Tail")
        parent=name
    end=h*.02+tail_length
    span=h*style["caudal"]
    if not span:
        pass
    elif style["fluke"]:
        b.bone("caudal",(0,end,z),(0,end+span*.45,z),parent,box=(w*.3,h*.02,span,h*.012),radius=h*.02,group="Tail")
    else:
        b.bone("caudal",(0,end,z),(0,end+span*.8,z),parent,box=(h*.014,d*.25,h*.01,span),radius=h*.02,group="Tail")
    if style.get("thin_tail"):
        # A translucent-looking fin runs along the top and bottom of the tail.
        for spec in b.bones:
            if spec["name"].startswith("tail."):
                w0,d0,w1,d1=spec["box"]
                spec["box"]=(w0*.45,d*.62,w1*.45,d*.50)
    middle=spine[min(len(spine)-1,len(spine)//3)]
    base=(0,-h*.02-front*.30,z+d*.42)
    rise=h*style["dorsal"]
    if rise: b.bone("dorsal",base,(0,base[1]+rise*.7,base[2]+rise),middle,box=(h*.014,rise*1.3,h*.008,rise*.35),
           radius=h*.012,group="Details")
    reach=h*style["fin"]
    for side,sign in (("L",1),("R",-1)) if reach else ():
        root=(sign*w*.42,-h*.02-front*.55,z-d*.22)
        tip=(root[0]+sign*reach*.55,root[1]+reach*.62,root[2]-reach*.55)
        mid=tuple((root[j]+tip[j])/2 for j in range(3))
        chord=reach*.62
        b.bone(f"fin.01.{side}",root,mid,spine[min(len(spine)-1,len(spine)//2)],
               box=(chord,h*.014,chord*.85,h*.012),radius=h*.014,group="Details")
        b.bone(f"fin.02.{side}",mid,tip,f"fin.01.{side}",box=(chord*.85,h*.012,chord*.3,h*.008),
               radius=h*.01,group="Details")
    return b

MECH_ARMOUR={
    # bone name prefix -> (width, depth) factors at the head and tail of its box
    "MECH_TROOPER":{"clavicle":(2.3,2.6,2.6,2.9),"arm.":(1.25,1.25,1.2,1.2),"forearm":(1.6,1.6,1.9,1.9),
        "hand":(2.2,1.3,2.2,1.2),"upper":(1.2,1.2,1.15,1.15),"lower":(1.35,1.4,2.0,2.1),"foot":(1.6,1.5,1.7,1.6),
        "toe":(1.7,1.6,1.6,1.5),"spine":(1.12,1.45,1.18,1.5),"pelvis":(1.0,1.3,.95,1.2),"head":(.78,.8,.7,.72),
        "neck":(.9,.9,.9,.9)},
    "MECH_FLYER":{"clavicle":(1.7,1.9,1.9,2.1),"arm.":(1.0,1.0,.95,.95),"forearm":(1.25,1.25,1.5,1.5),
        "hand":(1.8,1.1,1.8,1.0),"upper":(1.0,1.0,.95,.95),"lower":(1.2,1.3,2.2,2.4),"foot":(1.3,1.3,1.4,1.3),
        "toe":(1.3,1.3,1.1,1.1),"spine":(1.0,1.25,1.1,1.35),"pelvis":(.9,1.1,.85,1.0),"head":(.7,.85,.6,.7),
        "neck":(.8,.8,.8,.8)},
}

def armour(b,species):
    """Re-proportion the box figure into a mech: bulk in the shoulders,
    forearms and lower legs, a small head."""
    table=MECH_ARMOUR[species]
    for spec in b.bones:
        if not spec.get("box"):
            continue
        name=spec["name"]
        key=next((k for k in table if (name.endswith("."+k) if k in {"upper","lower","foot"} else name.startswith(k))),None)
        if key:
            spec["box"]=tuple(v*f for v,f in zip(spec["box"],table[key]))
            spec["radius"]=spec["radius"]*max(table[key])**.5
    h=b.size
    bones={spec["name"]:spec for spec in b.bones}
    heavy=species=="MECH_TROOPER"
    chest=sorted(n for n in bones if n.startswith("spine."))[-1]
    top=bones[chest]["tail"]
    # Armour plates: shoulder guards, a backpack and knee or thruster blocks.
    b.form(chest,(0,h*.085,top[2]-h*.05),(h*(.085 if heavy else .06),h*(.05 if heavy else .035),h*(.10 if heavy else .12)),1)
    for side,sign in (("L",1),("R",-1)):
        shoulder=bones["arm."+side]["head"]
        size=(h*.085,h*.075,h*.06) if heavy else (h*.055,h*.06,h*.045)
        b.form("arm."+side,(shoulder[0]+sign*h*.02,shoulder[1],shoulder[2]+h*.01),size,1)
        knee=bones[f"leg.01.{side}.lower"]["head"]
        ankle=bones[f"leg.01.{side}.foot"]["head"]
        if heavy:
            b.form(f"leg.01.{side}.lower",(knee[0],knee[1]-h*.03,knee[2]),(h*.04,h*.03,h*.05),1)
        else:
            b.form(f"leg.01.{side}.lower",(ankle[0],ankle[1]+h*.05,ankle[2]+h*.09),(h*.035,h*.04,h*.09),1)

def accessories(b,p):
    """Optional parts any creature can wear: tail on the biped, wings,
    antennae and a ponytail. Each is a short chain the motion system animates."""
    h=b.size
    bones={spec["name"]:spec for spec in b.bones}
    def chain(prefix,start,direction,length,links,parent,r0,r1,suffix=""):
        mag=sum(v*v for v in direction)**.5
        unit=tuple(v/mag for v in direction)
        for k in range(links):
            a=tuple(start[j]+unit[j]*length*k/links for j in range(3))
            c=tuple(start[j]+unit[j]*length*(k+1)/links for j in range(3))
            ra=r0+(r1-r0)*k/links
            rb=r0+(r1-r0)*(k+1)/links
            parent=b.bone(f"{prefix}.{k+1:02d}{suffix}",a,c,parent,radius=ra,group="Details",
                          box=(ra*2,ra*2,rb*2,rb*2))
    if p.species in ({"BIPED"}|set(MECH_ARMOUR)) and p.tail_links:
        pelvis=bones["pelvis"]["head"]
        chain("tail",(0,h*.05,pelvis[2]),(0,1,-.25),h*.55*p.tail_length,p.tail_links,"pelvis",h*.035,h*.008)
        for spec in b.bones:
            if spec["name"].startswith("tail."): spec["group"]="Tail"
    head=bones.get("head")
    if head and (p.antennae or p.ponytail or p.jaw or p.eyes):
        # Bounds of everything drawn on the head, so parts sit on its surface
        # however large the head has been made.
        points=[head["head"],head["tail"]]
        box=head.get("box")
        if box:
            half=max(box)*.5
            for end in (head["head"],head["tail"]):
                along=[abs(head["tail"][j]-head["head"][j]) for j in range(3)]
                axis=along.index(max(along))
                pad=[0 if j==axis else half for j in range(3)]
                points+=[tuple(end[j]-pad[j] for j in range(3)),tuple(end[j]+pad[j] for j in range(3))]
        for form in b.forms:
            if form["bone"]=="head":
                c,sc=form["center"],form["scale"]
                points+=[tuple(c[j]-sc[j] for j in range(3)),tuple(c[j]+sc[j] for j in range(3))]
        low=tuple(min(pt[j] for pt in points) for j in range(3))
        high=tuple(max(pt[j] for pt in points) for j in range(3))
        width,depth,tall=(high[j]-low[j] for j in range(3))
        middle=(low[1]+high[1])*.5
        if p.antennae:
            for side,sign in (("L",1),("R",-1)):
                chain("antenna",(sign*width*.22,middle-depth*.15,high[2]),(sign*.35,-.45,.82),
                      h*.22*p.antenna_length,p.antenna_links,"head",h*.008,h*.004,"."+side)
        if p.ponytail:
            chain("ponytail",(0,high[1],high[2]-tall*.25),(0,.45,-.9),h*.30,4,"head",h*.028,h*.010)
        if p.jaw and "jaw" not in bones:
            # A hinged lower jaw under the head, from the back of the skull to the chin.
            hinge=(0,middle+depth*.20,low[2]+tall*.22)
            chin=(0,low[1]+depth*.04,low[2]+tall*.02)
            b.bone("jaw",hinge,chin,"head",group="Details",radius=tall*.09,
                   box=(width*.62,tall*.20,width*.42,tall*.12))
    if p.wings:
        torso=sorted(n for n in bones if n.startswith("torso."))
        spine=sorted(n for n in bones if n.startswith("spine."))
        anchor=(torso or spine or ["pelvis"])[-1]
        point=bones[anchor]["tail"]
        upright=bones[anchor]["tail"][2]-bones[anchor]["head"][2]>abs(bones[anchor]["tail"][1]-bones[anchor]["head"][1])
        ay=point[1]+(h*.04 if upright else h*.10)
        az=point[2]-(h*.04 if upright else 0)+h*.03
        k=h*{"OSTRICH":.42,"BIRD":.6,"EAGLE":1.15,"MECH_FLYER":.85}.get(p.species,1.0)*p.wing_span
        count=max(2,p.wing_links)
        for side,sign in (("L",1),("R",-1)):
            root=(sign*h*.05,ay,az)
            elbow=(sign*k*.40,ay+k*.10,az+k*.22)
            tip=(sign*k*.78,ay+k*.28,az+k*.10)
            # The leading edge: "wing", any "wingmid" links, then "wingtip".
            # Every joint after the first carries a rib that holds the membrane.
            lengths=[sum((b1[j]-a1[j])**2 for j in range(3))**.5 for a1,b1 in ((root,elbow),(elbow,tip))]
            def along(t):
                distance=t*(lengths[0]+lengths[1])
                if distance<=lengths[0]:
                    f=distance/lengths[0]
                    return tuple(root[j]+(elbow[j]-root[j])*f for j in range(3))
                f=(distance-lengths[0])/lengths[1]
                return tuple(elbow[j]+(tip[j]-elbow[j])*f for j in range(3))
            # Two links keep the classic shoulder-elbow-tip shape; more share the edge evenly.
            joints=[root,elbow,tip] if count==2 else [along(i/count) for i in range(count+1)]
            parent=anchor
            for i in range(count):
                name="wing."+side if i==0 else "wingtip."+side if i==count-1 else f"wingmid.{i}.{side}"
                parent=b.bone(name,joints[i],joints[i+1],parent,radius=h*(.028-.012*i/count),group="Wings")
                if 0<i<count-1:
                    joint=joints[i]
                    end=(joint[0]*.92,ay+k*(.50+.10*i/count),az-k*.04)
                    b.bone(f"wingrib.{i}.{side}",joint,end,name,radius=h*.01,group="Wings")
            last=joints[count-1]
            for i in range(3):
                end=(sign*k*(.42+i*.13),ay+k*(.62-i*.08),az-k*.06)
                if count>2:
                    end=(last[0]+(tip[0]-last[0])*i*.45,end[1],end[2])
                b.bone(f"wingfinger.{i+1}.{side}",last,end,"wingtip."+side,radius=h*.01,group="Wings")
    if p.eyes and head:
        # Cartoon eyes: a ball on a short stalk above the head, free to bounce.
        size=h*.04*p.eye_size
        # Spacing 0 puts the eyes together, 1 at the edges of the head, more
        # pushes them out past it. Height 0 sits them on top; negative values
        # slide them down the sides of the head, positive values raise the stalks.
        out=max(width*.5*p.eye_spacing,size*1.02)
        along=low[1]+depth*(.5-.5*p.eye_forward)
        if p.eye_height>=0:
            lift=size*(.9+2.2*p.eye_height)
            anchor_z=high[2]
        else:
            lift=size*.2
            anchor_z=high[2]+tall*max(-1.0,p.eye_height)
            out=max(out,width*.5+size*.5)
        for side,sign in (("L",1),("R",-1)):
            base=(sign*min(out,width*.5) if p.eye_height>=0 else sign*width*.5,along,anchor_z-size*.2 if p.eye_height>=0 else anchor_z)
            top=(sign*out,along-size*.3,anchor_z+lift)
            b.bone(f"eye.01.{side}",base,top,"head",group="Details")
            b.form(f"eye.01.{side}",top,(size,size,size),0,ball="eye_white")
            b.form(f"eye.01.{side}",(top[0],top[1]-size*.72,top[2]),(size*.5,size*.42,size*.5),0,ball="eye_pupil")

def blueprint(p):
    if p.species=="BIPED":
        b=biped(p)
    elif p.species in MECH_ARMOUR:
        b=biped(p)
        b.species=p.species
        armour(b,p.species)
    elif p.species in THEROPODS:
        b=theropod(p)
    elif p.species in SWIMMERS:
        b=swimmer(p)
    else:
        b=creature(p)
        if len(b.limbs)>=4 and p.species not in {"SPIDER","CRAB","CENTIPEDE"} and (abs(p.front_legs-1)>1e-6 or abs(p.hind_legs-1)>1e-6):
            stance(b,p)
    accessories(b,p)
    return b

def stance(b,p):
    """Different heights for the front and hind legs. Every height is scaled by
    a factor that runs from the hind-leg value at the hips to the front-leg
    value at the shoulders, so the back slopes and the feet stay on the floor."""
    bones={spec["name"]:spec for spec in b.bones}
    first=min(l["index"] for l in b.limbs)
    last=max(l["index"] for l in b.limbs)
    front_y=min(bones[l["upper"]]["head"][1] for l in b.limbs if l["index"]==first)
    rear_y=max(bones[l["upper"]]["head"][1] for l in b.limbs if l["index"]==last)
    def factor(y):
        t=(y-front_y)/max(rear_y-front_y,1e-6)
        t=max(0.0,min(1.0,t))
        return p.front_legs+(p.hind_legs-p.front_legs)*t
    def move(point):
        return (point[0],point[1],point[2]*factor(point[1]))
    # A leg keeps one factor from hip to toe, or its knee would bend out of line.
    leg_factor={}
    for limb in b.limbs:
        f=factor(bones[limb["upper"]]["head"][1])
        for key in ("upper","lower","foot","control","pole"):
            leg_factor[limb[key]]=f
        toe=f"toe.{limb['index']+1:02d}.{'L' if limb['side']>0 else 'R'}"
        leg_factor[toe]=f
        limb["ankle"]=(limb["ankle"][0],limb["ankle"][1],limb["ankle"][2]*f)
        limb["knee"]=(limb["knee"][0],limb["knee"][1],limb["knee"][2]*f)
    for spec in b.bones:
        f=leg_factor.get(spec["name"])
        for key in ("head","tail"):
            spec[key]=(spec[key][0],spec[key][1],spec[key][2]*f) if f else move(spec[key])
    for form in b.forms:
        f=leg_factor.get(form["bone"])
        c=form["center"]
        form["center"]=(c[0],c[1],c[2]*f) if f else move(c)
    for limb in b.limbs:
        hip,ankle=bones[limb["upper"]]["head"],limb["ankle"]
        limb["reach"]=sum((hip[j]-ankle[j])**2 for j in range(3))**.5

def creature(p):
    species, h = p.species, p.size
    b = Blueprint(species, h)
    human = species in {"HUMAN", "APE", "MECH", "ANGEL", "ALIEN", "PENGUIN"}
    dinosaur = False
    sprawl = species in {"LIZARD", "GECKO", "FROG"}
    radial = species in {"SPIDER", "CRAB"}
    long = species == "CENTIPEDE"
    upright = human or dinosaur
    pairs = p.leg_pairs
    length = h * .48 * p.body_length
    width = h * .12 * p.body_width
    leg_height = h * (.48 if upright else .47) * p.leg_length
    if radial or long:
        leg_height *= .62
    z = leg_height + h*.06
    if sprawl:
        # Belly close to the ground, legs out to the sides.
        z = h*(.085+.05*p.leg_length)
    b.bone("CTRL-root", (0,0,0), (0,0,h*.12), deform=False, group="Controls")
    b.bone("CTRL-body", (0,0,z), (0,0,z+h*.12), "CTRL-root", False, group="Controls")
    level = not upright and not radial and not long
    rear = length*.42
    if level:
        # Four-legged bodies carry the hips at the back, lying along the spine.
        b.bone("pelvis", (0,rear+h*.11,z), (0,rear,z), "CTRL-body")
        b.form("pelvis", (0,rear+h*.035,z), (width*1.22*p.hip_size, h*.115, h*.122*p.hip_size), 0)
    else:
        b.bone("pelvis", (0,0,z), (0,0,z+h*.08), "CTRL-body")
        b.form("pelvis", (0,0,z), (width*1.16*p.hip_size, h*.10*p.hip_size, h*.09), 1)
    spine = []
    for i in range(p.spine_links):
        u0, u1 = i/p.spine_links, (i+1)/p.spine_links
        if upright:
            head, tail = (0,0,z+h*.25*u0), (0,0,z+h*.25*u1)
            g = girth(p,(u0+u1)/2)
            shape = (width*(1.0+u1*.42)*g, h*.073*g, h*.15/p.spine_links+h*.025)
        else:
            head = (0, length*.42-length*.84*u0, z)
            tail = (0, length*.42-length*.84*u1, z+h*.025*sin(pi*u1))
            g = girth(p,(u0+u1)/2) if level else 1.0
            shape = (width*(1.0+.18*sin(pi*u1))*g, length*.5/p.spine_links+h*.025, h*.11*g)
        name = f"spine.{i+1:02d}"
        b.bone(name, head, tail, spine[-1] if spine else "pelvis")
        center = tuple((head[j]+tail[j])/2 for j in range(3))
        b.form(name, center, shape, i % 2 if long else 0)
        spine.append(name)

    torso=[]
    if upright:
        neck_base = (0,0,z+h*.25)
        neck_top = (0,-h*.025 if dinosaur else 0,z+h*.32)
        head_center = (0, -h*.07 if dinosaur else -h*.005, z+h*.385)
        head_shape = (h*.072, h*(.13 if dinosaur else .065), h*.09)
    else:
        neck_base=(0,-length*.42,z)
        if species == "CENTAUR":
            # An upright torso rises from the front of the four-legged body.
            y0=-length*.42
            for i in range(3):
                a,c=(0,y0,z+h*.02+h*.10*i),(0,y0,z+h*.02+h*.10*(i+1))
                name=f"torso.{i+1:02d}"
                b.bone(name,a,c,torso[-1] if torso else spine[-1])
                b.form(name,(0,y0,(a[2]+c[2])/2),(width*(1.0+.22*i),h*.075,h*.065))
                torso.append(name)
            neck_base=(0,y0,z+h*.32)
            neck_top=(0,y0,z+h*.39)
            head_center=(0,y0-h*.005,z+h*.455)
            head_shape=(h*.072,h*.065,h*.09)
        elif species in {"HORSE", "GNOU", "GIRAFFE", "BRONTO"}:
            neck_top=(0,-length*.62,z+h*.27)
            head_center=(0,-length*.72,z+h*.30)
            head_shape=(h*.065,h*.115,h*.10)
        elif species == "LIZARD":
            neck_top=(0,-length*.54,z+h*.015)
            head_center=(0,-length*.68,z+h*.015)
            head_shape=(h*.065,h*.14,h*.047)
        elif species == "GORILLA":
            # A heavy head carried low and forward, with a crest on top.
            neck_top=(0,-length*.50,z+h*.04)
            head_center=(0,-length*.50-h*.07,z+h*.07)
            head_shape=(h*.085,h*.095,h*.10)
        elif species == "FROG":
            neck_top=(0,-length*.46,z+h*.03)
            head_center=(0,-length*.46-h*.085,z+h*.04)
            head_shape=(h*.115,h*.10,h*.062)
        elif species == "GECKO":
            neck_top=(0,-length*.50,z+h*.02)
            head_center=(0,-length*.50-h*.10,z+h*.025)
            head_shape=(h*.095,h*.115,h*.055)
        elif species == "CRAB":
            neck_top=(0,-length*.36,z)
            head_center=(0,-length*.38,z+h*.015)
            head_shape=(h*.13,h*.07,h*.045)
        else:
            neck_top=(0,-length*.54,z+h*.035)
            head_center=(0,-length*.65,z+h*.035)
            head_shape=(h*.10,h*.105,h*.075)
    stretch=tuple((neck_top[j]-neck_base[j])*(p.neck_length-1) for j in range(3))
    neck_top=tuple(neck_top[j]+stretch[j] for j in range(3))
    head_center=tuple(head_center[j]+stretch[j] for j in range(3))
    neck=neck_chain(b,[neck_base,neck_top],p.neck_links,torso[-1] if torso else spine[-1],h*.084,h*.07)
    for spec in b.bones:
        if spec["name"].startswith("neck"): spec["box"]=None   # this family draws round or default boxes
    b.bone("head", neck_top, (head_center[0], head_center[1]-h*.04, head_center[2]+h*.06), neck)
    head_shape=tuple(v*p.head_size for v in head_shape)
    b.form("head", head_center, head_shape)
    # A graphic face gives every creature a clear facing direction.
    for sign in (1,-1):
        eye=(sign*head_shape[0]*.77, head_center[1]-head_shape[1]*.62, head_center[2]+head_shape[2]*.25)
        b.form("head", eye, (h*.014,h*.016,h*.014), 2)
        if species in {"HORSE","PANTHER","DRAGON","GIRAFFE"}:
            ear=(sign*head_shape[0]*.75,head_center[1]+head_shape[1]*.2,head_center[2]+head_shape[2])
            b.form("head", ear, (h*.023,h*.023,h*.055), 1)

    def limb(prefix, hip, knee, ankle, parent, index, sign, foot_scale=1, ground=None, toe=None):
        """ground: where a digitigrade foot meets the floor. The foot bone then
        runs down from the raised ankle and a separate toe lies flat."""
        upper, lower, foot = prefix+".upper", prefix+".lower", prefix+".foot"
        r = h*(.025 if radial or long or sprawl else .038)
        b.bone(upper,hip,knee,parent,radius=r,group="Legs")
        b.bone(lower,knee,ankle,upper,radius=r*.72,group="Legs")
        if ground:
            end=ground
            b.bone(foot,ankle,ground,lower,radius=r*.55,group="Legs")
            tip=(ground[0],ground[1]-h*.065*foot_scale,ground[2]-h*.008)
            b.bone(f"toe.{index+1:02d}.{prefix[-1]}",ground,tip,foot,radius=r*.7,group="Legs")
        else:
            end=toe or (ankle[0],ankle[1]-h*.085*foot_scale,ankle[2]-h*.012)
            b.bone(foot,ankle,end,lower,radius=r*.8,group="Legs")
        control = "CTRL-"+prefix
        b.bone(control,ankle,end,"CTRL-root",False,group="Feet IK")
        # Project the rest knee out from the hip-ankle line for a stable plane.
        line=tuple(ankle[j]-hip[j] for j in range(3))
        t=sum((knee[j]-hip[j])*line[j] for j in range(3))/sum(v*v for v in line)
        projected=tuple(hip[j]+line[j]*t for j in range(3))
        direction=tuple(knee[j]-projected[j] for j in range(3))
        mag=sum(v*v for v in direction)**.5
        pole=tuple(knee[j]+direction[j]/max(mag,1e-6)*h*.25 for j in range(3))
        pole_name="POLE-"+prefix
        b.bone(pole_name,pole,(pole[0],pole[1],pole[2]+h*.05),"CTRL-root",False,group="Poles")
        b.limbs.append(dict(upper=upper,lower=lower,foot=foot,control=control,pole=pole_name,
            ankle=ankle,knee=knee,index=index,side=sign,reach=sum((hip[j]-ankle[j])**2 for j in range(3))**.5))
        b.form(upper,hip,(r*1.1,)*3,1)
        b.form(lower,knee,(r*.9,)*3,1)
        if not ground:
            b.form(foot,((ankle[0]+end[0])/2,(ankle[1]+end[1])/2,ankle[2]*.5),
                   (r*(1.5 if species=="GECKO" else .9),h*.06*foot_scale,ankle[2]*.5),1)

    for i in range(pairs):
        for side,sign in (("L",1),("R",-1)):
            ground=toe=None
            if upright:
                y=(i-(pairs-1)/2)*h*.17
                hip=(sign*width*.65,y,z)
                knee=(sign*width*.80,y-h*.045, h*.055+leg_height*.49)
                ankle=(sign*width*.83,y,h*.055)
                parent="pelvis"
            elif radial or long:
                u=i/max(1,pairs-1)
                y=length*(u-.5)*(.95 if long else .65)
                spread=h*(.34 if radial else .23)*p.leg_length
                rake=(u-.5)*h*.30 if radial else h*.025
                hip=(sign*width,y,z)
                knee=(sign*(width+spread*.58),y+rake*.5,z+h*.10)
                ankle=(sign*(width+spread),y+rake,h*.035)
                parent=spine[min(len(spine)-1,round((1-u)*(len(spine)-1)))]
            elif sprawl:
                # Upper leg out to the side, lower leg down: elbows point back,
                # knees point forward, feet splay outward.
                u=i/max(1,pairs-1)
                y=length*(u-.5)*.80
                front=i==0
                # A frog's hind legs are much longer than its front ones, and stay folded.
                reach_out=h*.17*p.leg_length
                hip=(sign*width*.9,y,z)
                knee=(sign*(width*.9+reach_out*.62),y+(h*.035 if front else -h*.045),z+h*.035)
                ankle=(sign*(width*.9+reach_out),y+(-h*.03 if front else h*.03),h*.03)
                if species=="FROG" and not front:
                    # Folded like a Z: the thigh runs forward beside the body, the shin back to the foot.
                    side_x=sign*(width*.9+h*.10*p.leg_length)
                    knee=(side_x,y-h*.21*p.leg_length,z+h*.03)
                    ankle=(side_x*1.08,y+h*.05,h*.03)
                toe=(ankle[0]+sign*h*.03,ankle[1]-h*.06,h*.012)
                parent=spine[-1] if front else "pelvis"
            else:
                # Front legs fold at a backward elbow, hind legs at a forward
                # stifle and a backward hock; both stand on a raised ankle.
                u=i/max(1,pairs-1)
                y=length*(u-.5)*.84
                front=i==0
                x=sign*width*1.05
                hip=(sign*width,y,z)
                if species=="GORILLA":
                    # Knuckle-walker: long straight arms in front, short flat-footed legs behind.
                    x=sign*width*(1.25 if front else .95)
                    hip=(sign*width*(1.15 if front else .8),y,z)
                    knee=(x,y+(h*.045 if front else -h*.07),z*.52)
                    ankle=(x,y,h*.055)
                    toe=(x,y-h*(.05 if front else .09),h*.02)
                elif front:
                    knee=(x,y+h*.06,z*.66)
                    ankle=(x,y-h*.012,z*.30)
                    ground=(x,y-h*.022,h*.03)
                else:
                    knee=(x,y-h*.085,z*.67)
                    ankle=(x,y+h*.075,z*.34)
                    ground=(x,y+h*.035,h*.03)
                parent=spine[-1] if front else "pelvis"
            limb(f"leg.{i+1:02d}.{side}",hip,knee,ankle,parent,i,sign, .55 if radial or long else 1,ground,toe)

    if upright or torso:
        ay=-length*.42 if torso else 0
        az=z+h*.30 if torso else z+h*.23
        for side,sign in (("L",1),("R",-1)):
            sh=(sign*width*1.22,ay,az)
            al=h*p.arm_length*.23
            elbow=(sh[0]+sign*al*.60,ay-h*.012,sh[2]-al*.50)
            wrist=(sh[0]+sign*al,ay-h*.035,sh[2]-al*1.05)
            b.bone("arm."+side,sh,elbow,torso[-1] if torso else spine[-1],radius=h*.031,group="Arms")
            b.bone("forearm."+side,elbow,wrist,"arm."+side,radius=h*.024,group="Arms")
            hand=(wrist[0]+sign*h*.025,wrist[1],wrist[2]-h*.055)
            b.bone("hand."+side,wrist,hand,"forearm."+side,radius=h*.026,group="Arms")
            b.form("hand."+side,hand,(h*.025,h*.024,h*.036),1)

    parent="pelvis"
    tail_length=h*{"LIZARD":.95,"GECKO":.42,"PANTHER":.62,"BRONTO":1.5}.get(species,.55)*p.tail_length
    for i in range(p.tail_links):
        u0,u1=i/p.tail_links,(i+1)/p.tail_links
        start_y=0 if upright else length*.42+(h*.11 if level else 0)
        head=(0,start_y+tail_length*u0,z-h*.10*u0)
        tail=(0,start_y+tail_length*u1,z-h*.10*u1+h*.06*sin(pi*u1))
        name=f"tail.{i+1:02d}"
        b.bone(name,head,tail,parent,radius=h*{"GECKO":.085,"BRONTO":.10}.get(species,.06)*(1-u0*.86),group="Tail")
        parent=name

    # Independently designed silhouettes for the expanded creature library.
    if species == "GNOU":
        for side,sign in (("L",1),("R",-1)):
            a=(sign*head_shape[0]*.8,head_center[1],head_center[2]+head_shape[2]*.6)
            tip=(sign*h*.16,head_center[1]+h*.015,head_center[2]+h*.18)
            b.bone("horn."+side,a,tip,"head",radius=h*.018,group="Details")
        b.form("spine.01",(0,length*.10,z+h*.10),(width*1.3,h*.20,h*.16))
    elif species == "ALIEN":
        b.form("head",(0,head_center[1]+h*.025,head_center[2]+h*.05),
               (h*.075,h*.13,h*.11))
    elif species == "CRAB":
        b.form("pelvis",(0,0,z),(h*.26,h*.20,h*.085))
        for side,sign in (("L",1),("R",-1)):
            a=(sign*h*.15,-length*.25,z)
            elbow=(sign*h*.30,-length*.60,z+h*.04)
            tip=(sign*h*.23,-length*.93,z+h*.06)
            b.bone("clawarm."+side,a,elbow,"pelvis",radius=h*.025,group="Claws")
            b.bone("claw."+side,elbow,tip,"clawarm."+side,radius=h*.035,group="Claws")
            b.form("claw."+side,tip,(h*.075,h*.09,h*.04),1)
            for j in (-1,1):
                end=(tip[0]+j*h*.04,tip[1]-h*.13,tip[2])
                b.bone(f"pincer.{j}.{side}",tip,end,"claw."+side,radius=h*.016,group="Claws")
    elif species == "PENGUIN":
        tip=(0,head_center[1]-head_shape[1]-h*.07,head_center[2]-h*.01)
        b.bone("beak",(0,head_center[1]-head_shape[1]*.8,head_center[2]),tip,"head",radius=h*.014,group="Details")
        b.form("pelvis",(0,h*.01,z+h*.10),(width*1.15,h*.11,h*.17))
    elif species == "MECH":
        for side,sign in (("L",1),("R",-1)):
            b.form("arm."+side,(sign*width*1.35,0,z+h*.22),(h*.085,)*3,1)
        b.form("pelvis",(0,-h*.04,z+h*.07),(width*1.2,h*.09,h*.07),1)
    return b
